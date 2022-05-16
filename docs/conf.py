# -- Path setup --------------------------------------------------------------
import os
import sys
sys.path.insert(0, os.path.abspath('../'))

import flask_gatekeeper

# -- Project information -----------------------------------------------------

project = 'flask-gatekeeper'
copyright = '2022, k0rventen'
author = 'k0rventen'

# Configuration file for the Sphinx documentation builder.

version = flask_gatekeeper.__version__
release = flask_gatekeeper.__version__


extensions = ['sphinx.ext.autodoc','sphinx.ext.viewcode','sphinx.ext.napoleon', 'sphinx.ext.todo','sphinx_copybutton']

add_module_names = False

html_theme = 'sphinx_rtd_theme'
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
