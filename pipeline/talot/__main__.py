"""Talojen yöajo: python -m pipeline.talot --out dist --work work --cache cache"""
import sys

from .build import main

main(sys.argv[1:])
