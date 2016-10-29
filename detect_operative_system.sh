#!/bin/bash
# Detects which OS and if it is Linux then it will detect which Linux
# Distribution.

foobar_command_name=em++
if ! type "$foobar_command_name" > /dev/null;
then
	OS=`uname -s`
	REV=`uname -r`
	MACH=`uname -m`
	OSSTR=$(uname | tr "[:upper:]" "[:lower:]")
	if [ "${OS}" = "SunOS" ] ; then
		OS=Solaris
		ARCH=`uname -p` 
		OSSTR="${OS} ${REV}(${ARCH} `uname -v`)"
	elif [ "${OS}" = "AIX" ] ; then
		OSSTR="${OS} `oslevel` (`oslevel -r`)"
	elif [ "${OS}" = "Linux" ] ; then
		KERNEL=`uname -r`
		if [ -f /etc/redhat-release ] ; then
		DIST='Redhat'
		PSUEDONAME=`cat /etc/redhat-release | sed s/.*\(// | sed s/\)//`
		REV=`cat /etc/redhat-release | sed s/.*release\ // | sed s/\ .*//`
		elif [ -f /etc/SuSE-release ] ; then
		DIST=`cat /etc/SuSE-release | tr "\n" ' '| sed s/VERSION.*//`
		REV=`cat /etc/SuSE-release | tr "\n" ' ' | sed s/.*=\ //`
		elif [ -f /etc/mandrake-release ] ; then
		DIST='Mandrake'
		PSUEDONAME=`cat /etc/mandrake-release | sed s/.*\(// | sed s/\)//`
		REV=`cat /etc/mandrake-release | sed s/.*release\ // | sed s/\ .*//`
		elif [ -f /etc/debian_version ] ; then
		#DIST="Debian_`cat /etc/debian_version | tr "/" '_'`"
		if [ -f "/etc/lsb-release" -o -d "/etc/lsb-release.d" ] ; then
			DIST=$(lsb_release -ic | cut -d: -f2 | sed s/'^\t'// | tr '\n' '_' | sed s/'_$'//)
		else
			DIST=$(ls -d /etc/[A-Za-z]*[_-][rv]e[lr]* | grep -v "lsb" | cut -d'/' -f3 | cut -d'-' -f1 | cut -d'_' -f1 | tr '\n' '_' | sed s/'_$'//)
		fi
		REV=""

		fi
		if [ -f /etc/UnitedLinux-release ] ; then
		DIST="${DIST}[`cat /etc/UnitedLinux-release | tr "\n" ' ' | sed s/VERSION.*//`]"
		fi

		OSSTR="${OS}_${DIST}_${REV}${PSUEDONAME}${MACH}"
	fi
else
	OSSTR="emscripten"
fi

echo $OSSTR

