#!/bin/sh
# regress.sh SRCDIR TSTFILE [OPTIONS ...]
#
# Use ../src/interface/gnugo to run test TSTFILE in SRCDIR (first changing
# directory to SRCDIR).  OPTIONS are passed directly to gnugo.

if test ! "$GNUGO" ; then
	GNUGO=`pwd`/../build/src/interface/gnugo
	if test ! -x "$GNUGO" ; then
		echo ERROR: no such program: $GNUGO
		exit 1
	fi
fi

srcdir=$1
tstfile=$2
shift
shift

awkfile=`cd "$(dirname "$0")" && pwd`/regress.awk
cd $srcdir
$GNUGO --quiet "$@" --mode gtp < $tstfile \
	| awk -f "$awkfile" tst=$tstfile url=$GNUGO_REGRESSION_URL

# regress.sh ends here
