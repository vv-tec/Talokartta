"""Metsätilojen yöajo (Metsakartta): python -m pipeline.metsa --out dist --cache cache --work work"""
import sys

from .ajo import main

main(sys.argv[1:])
