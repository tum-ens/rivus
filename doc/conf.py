# -*- coding: utf-8 -*-

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx.ext.mathjax',
]

#templates_path = ['_templates']
source_suffix = '.rst'
master_doc = 'index'

project = u'rivus'
copyright = u'2015, ojdo'
version = '0.1'
release = '0.1'

exclude_patterns = ['_build']
#pygments_style = 'sphinx'

# HTML output

htmlhelp_basename = 'rivusdoc'

# LaTeX output

latex_elements = {
    'papersize': 'a4paper',
    'pointsize': '11pt',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [
  ('index', 'rivus.tex', u'rivus Documentation',
   u'ojdo', 'manual'),
]

# Manual page output

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ('index', 'rivus', u'rivus Documentation',
     [u'ojdo'], 1)
]


# Texinfo output

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
  ('index', 'rivus', u'rivus  Documentation',
   u'ojdo', 'rivus', 'A mixed integer linear optimisation model for energy infrastructure networks',
   'Miscellaneous'),
]


# Epub output

# Bibliographic Dublin Core info.
epub_title = u'rivus'
epub_author = u'ojdo'
epub_publisher = u'ojdo'
epub_copyright = u'2015, ojdo'

epub_exclude_files = ['search.html']


# Intersphinx

# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {
    'http://docs.python.org/': None,
    'pandas': ('http://pandas.pydata.org/pandas-docs/stable/', None),
    'matplotlib': ('http://matplotlib.org/', None)}

