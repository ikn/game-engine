from distutils.core import setup, Extension

setup(ext_modules = [Extension('_gm', sources = ['game/gm.c'])])
