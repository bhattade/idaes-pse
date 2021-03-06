##############################################################################
# Institute for the Design of Advanced Energy Systems Process Systems
# Engineering Framework (IDAES PSE Framework) Copyright (c) 2018-2019, by the
# software owners: The Regents of the University of California, through
# Lawrence Berkeley National Laboratory,  National Technology & Engineering
# Solutions of Sandia, LLC, Carnegie Mellon University, West Virginia
# University Research Corporation, et al. All rights reserved.
#
# Please see the files COPYRIGHT.txt and LICENSE.txt for full copyright and
# license information, respectively. Both files are also available online
# at the URL "https://github.com/IDAES/idaes-pse".
##############################################################################
"""
Find documentation for modules and classes in the
generated Sphinx documentation and return its location.
"""
# stdlib
import logging
import os
import types
# third-party
from lxml import html

__author__ = 'Dan Gunter <dkgunter@lbl.gov>'

_log = logging.getLogger(__name__)


def find_html_docs(dmf, obj=None, obj_name=None, **kw):
    """Get one or more files with HTML documentation for
    the given object, in paths referred to by the dmf instance.
    """
    if obj_name is None:
        module_, name = _get_object_name(obj)
    else:
        if obj_name.endswith('.'):
            module_, name = obj_name[:-1], ''
        else:
            try:
                module_, name = obj_name.rsplit('.', 1)
            except ValueError:
                raise
    _log.debug('Find docs for object. module=/{}/ name=/{}/'
               .format(module_, name))
    return get_html_docs(dmf, module_, name, **kw)


def get_html_docs(dmf, module_, name, sphinx_version=(1, 5, 5)):
    paths = dmf.get_doc_paths()
    if not paths:
        raise ValueError('No documentation locations configured')

    _log.info('find HTML docs for module={} class={} on paths={}'
              .format(module_, name, paths))
    filenames = []
    for p in paths:
        _log.debug('examine help path "{}"'.format(p))
        html_file = os.path.join(p, 'genindex.html')
        if os.path.exists(html_file):
            _log.debug('get_html_docs: find refs in file={}'.format(html_file))
            # Open and parse the index file into a 'tree'
            html_content = open(html_file).read()
            tree = html.fromstring(html_content)
            # Look for manual references first
            refs = _find_refs(tree, module_, name, sphinx_version)
            # Get full paths for relative refs
            if refs:
                ref = _pick_best_ref(refs)
                if os.path.isabs(p):
                    filenames = [os.path.join(p, ref)]
                else:
                    filenames = [os.path.join(dmf.root, p, ref)]
                break
        else:
            _log.debug('No "genindex.html" found at path "{}"'.format(p))
    return filenames


def _get_object_name(obj):
    if isinstance(obj, types.ModuleType):
        module, name = obj.__name__, ''
    else:
        if hasattr(obj, '_orig_module'):
            module = obj._orig_module
        else:
            module = obj.__module__
        if hasattr(obj, '_orig_name'):
            name = obj._orig_name
        elif isinstance(obj, type):
            name = obj.__name__  # class name of a class
        else:
            name = obj.__class__.__name__
    return module, name


def _find_refs(tree, module, name, sphinx_version):
    """Find object/etc. refs in the HTML.
    """
    # There are 3 types of refs we are looking for
    # 1. manually added with index directive
    xpath_expr = '//li[contains(.,"{m}")]/ul/li/a'.format(m=module)
    _log.debug('manually indexed: xpath expr={}'.format(xpath_expr))
    elements = tree.xpath(xpath_expr)
    hrefs = [e.get('href') for e in elements if e.text.strip() == name]
    if hrefs:
        _log.debug('found manually indexed docs at: {}'.format(hrefs[0]))
        return hrefs  # found something; stop
    if name:
        # 2a. embedded in the page
        target = '{}.{}'.format(module, name)
        subtype = 'embedded'  # for logging
    else:
        # 2b. generated by autodoc in the apidoc folder
        target = 'module-{}'.format(module)  # how Sphinx names these
        subtype = 'autodoc'  # for logging
    xpath_expr = '//li/a[contains(@href,"#{}")]/@href'.format(target)
    _log.debug('{}: xpath expr={}'.format(subtype, xpath_expr))
    hrefs = [p for p in tree.xpath(xpath_expr) if p.endswith(target)]
    if hrefs:
        _log.debug('found {} docs at: {}'.format(subtype, hrefs[0]))
    return hrefs


def _pick_best_ref(refs):
    # trivial case:q
    if len(refs) == 1:
        return refs[0]
    # find any non-apidoc ref
    for r in refs:
        if not r.startswith('apidoc'):
            return r
    # otherwise just return first
    return refs[0]
