#!/usr/bin/python

"""
Prototype of a module that can generate a HGVS description of the variant(s)
leading from one sequence to an other.

@requires: Bio.Seq
""" 
import collections
from Bio import Seq
from Bio.SeqUtils import seq3
from Bio.Data import CodonTable

from mutalyzer.util import longest_common_prefix, longest_common_suffix
from mutalyzer.util import palinsnoop, roll
from mutalyzer import models

from extractor import extractor

def makeFSTables(table_id):
    """
    For every pair of amino acids, calculate the set of possible amino acids in
    a different reading frame. Do this for both alternative reading frames (+1
    and +2).

    @arg table_id: Coding table ID.
    @type table_id: int
    @returns: Two dictionaries for the two alternative reading frames.
    @rtype: tuple(dict, dict)
    """
    # Make the forward translation table.
    table = dict(CodonTable.unambiguous_dna_by_id[table_id].forward_table)
    for i in CodonTable.unambiguous_dna_by_id[table_id].stop_codons:
        table[i] = '*'

    # Make the reverse translation table.
    reverse_table = collections.defaultdict(list)
    for i in table:
        reverse_table[table[i]].append(i)

    # Make the frame shift tables.
    FS1 = collections.defaultdict(set)
    FS2 = collections.defaultdict(set)
    for AA_i in reverse_table:
        for AA_j in reverse_table:
            for codon_i in reverse_table[AA_i]:
                for codon_j in reverse_table[AA_j]:
                    FS1[AA_i + AA_j].add(table[(codon_i + codon_j)[1:4]]) # +1.
                    FS2[AA_i + AA_j].add(table[(codon_i + codon_j)[2:5]]) # +2.
                #for
    return FS1, FS2
#makeFSTables

def __makeOverlaps(peptide):
    """
    Make a list of overlapping 2-mers of {peptide} in order of appearance.

    @arg peptide: A peptide sequence.
    @type peptide: str
    @returns: All 2-mers of {peptide} in order of appearance.
    @rtype: list(str)
    """
    return map(lambda x: peptide[x:x+2], range(len(peptide) - 1))
#__makeOverlaps

def __options(pList, peptidePrefix, FS, output):
    """
    Enumerate all peptides that could result from a frame shift.

    @arg pList: List of overlapping 2-mers of a peptide.
    @type pList: list(str)
    @arg peptidePrefix: Prefix of a peptide in the alternative reading frame.
    @type peptidePrefix: str
    @arg FS: Frame shift table.
    @type FS: dict
    @arg output: List of peptides, should be empty initially.
    @type output: list(str)
    """
    if not pList:
        output.append(peptidePrefix)
        return
    #if
    for i in FS[pList[0]]:
        __options(pList[1:], peptidePrefix + i, FS, output)
#__options

def enumFS(peptide, FS):
    """
    Enumerate all peptides that could result from a frame shift.

    @arg peptide: Original peptide sequence.
    @type peptide: str
    @arg FS: Frame shift table.
    @type FS: dict
    """
    output = []

    __options(__makeOverlaps(peptide), "", FS, output)
    return output
#enumFS

def fitFS(peptide, altPeptide, FS):
    """
    Check whether peptide {altPeptide} is a possible frame shift of peptide
    {peptide}.

    @arg peptide: Original peptide sequence.
    @type peptide: str
    @arg altPeptide: Observed peptide sequence.
    @type altPeptide: str
    @arg FS: Frame shift table.
    @type FS: dict
    """
    # Todo: This is a temporary fix to prevent crashing on frameshift
    #     detection (I think bug #124).
    return False

    if len(peptide) < len(altPeptide):
        return False

    pList = __makeOverlaps(peptide)

    for i in range(len(altPeptide)):
        if not altPeptide[i] in FS[pList[i]]:
            return False
    return True
#fitFS

def findFS(peptide, altPeptide, FS):
    """
    Find the longest part of {altPeptide} that fits in {peptide} in a certain
    frame given by {FS}.

    @arg peptide: Original peptide sequence.
    @type peptide: str
    @arg altPeptide: Observed peptide sequence.
    @type altPeptide: str
    @arg FS: Frame shift table.
    @type FS: dict

    @returns: The length and the offset in {peptide} of the largest frameshift.
    @rtype: tuple(int, int)
    """
    pList = __makeOverlaps(peptide)
    maxFS = 0
    fsStart = 0
    
    for i in range(len(pList))[::-1]:
        for j in range(min(i + 1, len(altPeptide))):
            if not altPeptide[::-1][j] in FS[pList[i - j]]:
                break
        if j >= maxFS:
            maxFS = j
            fsStart = i - j + 2
        #if
    #for

    return maxFS - 1, fsStart
#findFS

class RawVar(models.RawVar):
    """
    Container for a raw variant.

    To use this class correctly, do not supply more than the minimum amount of
    data. The {description()} function may not work properly if too much
    information is given.

    Example: if {end} is initialised for a substitution, a range will be
      retuned, resulting in a description like: 100_100A>T
    """

    def __init__(self, DNA=True, start=0, start_offset=0, end=0, end_offset=0,
        type="none", deleted="", inserted="", shift=0, startAA="", endAA="",
        term=0):
        """
        Initialise the class with the appropriate values.

        @arg start: Start position.
        @type start: int
        @arg start_offset:
        @type start_offset: int
        @arg end: End position.
        @type end: int
        @arg end_offset:
        @type end_offset: int
        @arg type: Variant type.
        @type type: str
        @arg deleted: Deleted part of the reference sequence.
        @type deleted: str
        @arg inserted: Inserted part.
        @type inserted: str
        @arg shift: Amount of freedom.
        @type shift: int
        """
        # TODO: Will this container be used for all variants, or only genomic?
        #       start_offset and end_offset may be never used.
        self.DNA = DNA
        self.start = start
        self.start_offset = start_offset
        self.end = end
        self.end_offset = end_offset
        self.type = type
        self.deleted = deleted
        self.inserted = inserted
        self.shift = shift
        self.startAA = startAA
        self.endAA = endAA
        self.term = term
        self.update()
        #self.hgvs = self.description()
        #self.hgvsLength = self.descriptionLength()
    #__init__

    def __DNADescription(self):
        """
        Give the HGVS description of the raw variant stored in this class.

        Note that this function relies on the absence of values to make the
        correct description. Also see the comment in the class definition.

        @returns: The HGVS description of the raw variant stored in this class.
        @rtype: str
        """
        if not self.start:
            return "="

        descr = "%i" % self.start

        if self.end:
            descr += "_%i" % self.end

        if self.type != "subst":
            descr += "%s" % self.type

            if self.inserted:
                return descr + "%s" % self.inserted
            return descr
        #if

        return descr + "%s>%s" % (self.deleted, self.inserted)
    #__DNADescription

    def __proteinDescription(self):
        """
        Give the HGVS description of the raw variant stored in this class.

        Note that this function relies on the absence of values to make the
        correct description. Also see the comment in the class definition.

        @returns: The HGVS description of the raw variant stored in this class.
        @rtype: str
        """
        if self.type == "unknown":
            return "?"
        if not self.start:
            return "="

        descr = ""
        if not self.deleted:
            if self.type == "ext":
                descr += '*'
            else:
                descr += "%s" % seq3(self.startAA)
        #if
        else:
            descr += "%s" % seq3(self.deleted)
        descr += "%i" % self.start
        if self.end:
            descr += "_%s%i" % (seq3(self.endAA), self.end)
        if self.type not in ["subst", "stop", "ext", "fs"]: # fs is not a type
            descr += self.type
        if self.inserted:
            descr += "%s" % seq3(self.inserted)

        if self.type == "stop":
            return descr + '*'
        if self.term:
            return descr + "fs*%i" % self.term
        return descr
    #__proteinDescription

    def __DNADescriptionLength(self):
        """
        Give the standardised length of the HGVS description of the raw variant
        stored in this class.

        Note that this function relies on the absence of values to make the
        correct description. Also see the comment in the class definition.

        @returns: The standardised length of the HGVS description of the raw
            variant stored in this class.
        @rtype: int
        """
        if not self.start: # `=' or `?'
            return 1

        descrLen = 1 # Start position.

        if self.end: # '_' and end position.
            descrLen += 2

        if self.type != "subst":
            descrLen += len(self.type)

            if self.inserted:
                return descrLen + len(self.inserted)
            return descrLen
        #if

        return 4 # Start position, '>' and end position.
    #__DNAdescriptionLength

    def __proteinDescriptionLength(self):
        """
        Give the standardised length of the HGVS description of the raw variant
        stored in this class.

        Note that this function relies on the absence of values to make the
        correct description. Also see the comment in the class definition.

        @returns: The standardised length of the HGVS description of the raw
            variant stored in this class.
        @rtype: int
        """
        if not self.start: # =
            return 1

        descrLen = 1      # Start position.
        if not self.deleted and self.type == "ext":
            descrLen += 1 # *
        else:
            descrLen += 3 # One amino acid.
        if self.end:
            descrLen += 5 # `_' + one amino acid + end position.
        if self.type not in ["subst", "stop", "ext", "fs"]:
            descrLen += len(self.type)
        if self.inserted:
            descrLen += 3 * len(self.inserted)
        if self.type == "stop":
            return descrLen + 1 # *
        if self.term:
            return descrLen + len(self.type) + 2 # `*' + length until stop.
        return descrLen
    #__proteinDescriptionLength

    def update(self):
        """
        """
        self.hgvs = self.description()
        self.hgvsLength = self.descriptionLength()
    #update

    def description(self):
        """
        """
        if self.DNA:
            return self.__DNADescription()
        return self.__proteinDescription()
    #description

    def descriptionLength(self):
        """
        Give the standardised length of the HGVS description of the raw variant
        stored in this class.

        @returns: The standardised length of the HGVS description of the raw
            variant stored in this class.
        @rtype: int
        """
        if self.DNA:
            return self.__DNADescriptionLength()
        return self.__proteinDescriptionLength()
    #descriptionLength
#RawVar

def alleleDescription(allele):
    """
    Convert a list of raw variants to an HGVS allele description.

    @arg allele: A list of raw variants representing an allele description.
    @type allele: list(RawVar)

    @returns: The HGVS description of {allele}.
    @rval: str
    """
    if len(allele) > 1:
        return "[%s]" % ';'.join(map(lambda x: x.hgvs, allele))
    return allele[0].hgvs
#alleleDescription

def alleleDescriptionLength(allele):
    """
    Calculate the standardised length of an HGVS allele description.

    @arg allele: A list of raw variants representing an allele description.
    @type allele: list(RawVar)

    @returns: The standardised length of the HGVS description of {allele}.
    @rval: int
    """
    # NOTE: Do we need to count the ; and [] ?
    return sum(map(lambda x: x.hgvsLength, allele))
#alleleDescriptionLength

def printpos(s, start, end, fill=0):
    """
    For debugging purposes.
    """
    # TODO: See if this can partially replace or be merged with the
    #       visualisation in the __mutate() function of mutator.py
    fs = 10 # Flank size.

    return "%s %s%s %s" % (s[start - fs:start], s[start:end], '-' * fill,
        s[end:end + fs])
#printpos

def var2RawVar(s1, s2, var, DNA=True):
    """
    """
    # Unknown.
    if s1 == '?' or s2 == '?':
        return [RawVar(DNA=DNA, type="unknown")]

    # Insertion / Duplication.
    if var.reference_start == var.reference_end:
        ins_length = var.sample_end - var.sample_start
        shift5, shift3 = roll(s2, var.sample_start + 1, var.sample_end)
        shift = shift5 + shift3

        var.reference_start += shift3
        var.reference_end += shift3
        var.sample_start += shift3
        var.sample_end += shift3

        if (var.sample_start - ins_length >= 0 and
            s1[var.reference_start - ins_length:var.reference_start] ==
            s2[var.sample_start:var.sample_end]):

            if ins_length == 1:
                return RawVar(DNA=DNA, start=var.reference_start, type="dup",
                    shift=shift)
            return RawVar(DNA=DNA, start=var.reference_start - ins_length + 1,
                end=var.reference_end, type="dup", shift=shift)
        #if
        return RawVar(DNA=DNA, start=var.reference_start,
            end=var.reference_start + 1,
            inserted=s2[var.sample_start:var.sample_end], type="ins",
            shift=shift)
    #if

    # Deletion.
    if var.sample_start == var.sample_end:
        shift5, shift3 = roll(s1, var.reference_start + 1, var.reference_end)
        shift = shift5 + shift3

        var.reference_start += shift3 + 1
        var.reference_end += shift3

        if var.reference_start == var.reference_end:
            return RawVar(DNA=DNA, start=var.reference_start, type="del",
                shift=shift)
        return RawVar(DNA=DNA, start=var.reference_start,
            end=var.reference_end, type="del", shift=shift)
    #if

    # Substitution.
    if (var.reference_start + 1 == var.reference_end and
        var.sample_start + 1 == var.sample_end):

        return RawVar(DNA=DNA, start=var.reference_start + 1,
            deleted=s1[var.reference_start], inserted=s2[var.sample_start],
            type="subst")
    #if

    # Simple InDel.
    if var.reference_start + 1 == var.reference_end:
        return RawVar(DNA=DNA, start=var.reference_start + 1,
            inserted=s2[var.sample_start:var.sample_end], type="delins")

    # Inversion.
    if var.type == extractor.VARIANT_REVERSE_COMPLEMENT:
        trim = palinsnoop(s1[var.reference_start:var.reference_end])

        if trim > 0: # Partial palindrome.
            var.reference_end -= trim
            var.sample_end -= trim
        #if

        return RawVar(DNA=DNA, start=var.reference_start + 1,
            end=var.reference_end, type="inv")
    #if

    # InDel.
    return RawVar(DNA=DNA, start=var.reference_start + 1,
        end=var.reference_end, inserted=s2[var.sample_start:var.sample_end],
        type="delins")
#var2RawVar

def description(s1, s2, DNA=True):
    """
    Give an allele description of the change from {s1} to {s2}.

    arg s1: Sequence 1.
    type s1: str
    arg s2: Sequence 2.
    type s2: str

    @returns: A list of RawVar objects, representing the allele.
    @rval: list(RawVar)
    """
    description = []

    if not DNA:
        FS1, FS2 = makeFSTables(1)
        longestFSf = max(findFS(s1, s2, FS1), findFS(s1, s2, FS2))
        longestFSr = max(findFS(s2, s1, FS1), findFS(s2, s1, FS2))

        if longestFSf > longestFSr:
            print s1[:longestFSf[1]], s1[longestFSf[1]:]
            print s2[:len(s2) - longestFSf[0]], s2[len(s2) - longestFSf[0]:]
            s1_part = s1[:longestFSf[1]]
            s2_part = s2[:len(s2) - longestFSf[0]]
            term = longestFSf[0]
        #if
        else:
            print s1[:len(s1) - longestFSr[0]], s1[len(s1) - longestFSr[0]:]
            print s2[:longestFSr[1]], s2[longestFSr[1]:]
            s1_part = s1[:len(s1) - longestFSr[0]]
            s2_part = s2[:longestFSr[1]]
            term = len(s2) - longestFSr[1]
        #else

        s1_part = s1
        s2_part = s2
        for variant in extractor.extract(str(s1_part), len(s1_part),
            str(s2_part), len(s2_part), 1):
            description.append(var2RawVar(s1, s2, variant, DNA=DNA))

        if description:
            description[-1].term = term + 2
            description[-1].update()
        #if
    #if
    else:
        for variant in extractor.extract(str(s1), len(s1), str(s2), len(s2),
            0):
            if variant.type != extractor.VARIANT_IDENTITY:
                description.append(var2RawVar(s1, s2, variant, DNA=DNA))

    # Nothing happened.
    if not description:
        return [RawVar(DNA=DNA)]

    return description
#description

if __name__ == "__main__":
    a = "ATAGATGATAGATAGATAGAT"
    b = "ATAGATGATTGATAGATAGAT"
    print alleleDescription(description(a, b, DNA=True))

    a = "MAVLWRLSAVCGALGGRALLLRTPVVRPAH"
    b = "MAVLWRLSAGCGALGGRALLLRTPVVRAH"
    print alleleDescription(description(a, b, DNA=False))

    a = "MDYSLAAALTLHGHWGLGQVVTDYVHGDALQKAAKAGLLALSALTFAGLCYFNYHDVGICKAVAMLWKL"
    b = "MDYSLAAALTFMVTGALDKLLLTMFMGMPCRKLPRQGFWHFQL"
    #print alleleDescription(description(a, b, DNA=False))
    #print alleleDescription(description(b, a, DNA=False))
    print "1"
    extractor.extract(a, len(a), b, len(b), 1)
    print "2"
    extractor.extract(b, len(b), a, len(a), 1)
    print "3"


    a = "VVSVLLLGLLPAAYLNPCSAMYYSLAAALTLHGHWGLGQV"
    b = "VVSVLLLGLLPAAYLNPCSAMDYSLAAALTLHGHWGLGQV"
    print alleleDescription(description(a, b, DNA=False))
    print alleleDescription(description(b, a, DNA=False))

    a = "ACGCTCGATCGCTTATAGCATGGGGGGGGGATCTAGCTCTCTCTATAAGATA"
    b = "ACGCTCGATCGCTTATACCCCCCCCATGCGATCTAGCTCTCTCTATAAGATA"
    print alleleDescription(description(a, b, DNA=True))

#if