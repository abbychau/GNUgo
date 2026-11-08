#!/bin/sh
nice -n 19 perl "$(dirname "$0")/regress.pl" \
  --verbose 1  \
  -a 1
