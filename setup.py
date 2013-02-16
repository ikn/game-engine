from distutils.core import setup, Extension

setup(ext_modules = [Extension('gmdraw', sources = ['game/gmdraw.c'])])
