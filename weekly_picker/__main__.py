import sys

from weekly_picker.commands import main

text = main(sys.argv[1:])
if text:
    print(text)
