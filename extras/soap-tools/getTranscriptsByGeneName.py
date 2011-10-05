#!/usr/bin/env python
"""
Get transcript accession numbers for a gene.

Usage:
  {command} gene

  gene: Gene name to lookup transcripts for.

The transcript accession numbers are retrieved from the Mutalyzer SOAP
webservice and printed to standard output.
"""


from mutalyzer.util import monkey_patch_suds; monkey_patch_suds()

import sys
from suds.client import Client

from mutalyzer.util import format_usage


WSDL_LOCATION = 'http://localhost/mutalyzer/services/?wsdl'


def main(gene):
    """
    Get transcript accession numbers and print them to standard output.
    """
    service = Client(WSDL_LOCATION, cache=None).service
    result = service.getTranscriptsByGeneName('hg19', gene)

    if result:
        for transcript in result.string:
            print transcript


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print format_usage()
        sys.exit(1)
    main(sys.argv[1])