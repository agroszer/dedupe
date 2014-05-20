dedupe
======

Deduplicate files by replacing them with symlinks

Usage: dedupe source repository

Options:
  -h, --help            show this help message and exit
  -v, --verbose         Be more verbose (can be repeated)
  -l LOGFILE, --log=LOGFILE
                        Specify a log file to write
  -s SAVE_BACKLINKS, --save=SAVE_BACKLINKS
                        Save backlinks to repo root
  -m USE_MOVE, --move=USE_MOVE
                        Try move instead of copy when adding to repo
  --tests               Run tests
