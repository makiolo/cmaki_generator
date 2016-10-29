project(gtc)
cmake_minimum_required(VERSION 2.8)

get_filename_component(BASEDIR "${CMAKE_CURRENT_LIST_FILE}" PATH)
include("${BASEDIR}/../cmaki.cmake")

SET(GLOBAL_COMPILER "${CMAKI_COMPILER}")
SET(GLOBAL_PLATFORM "${CMAKI_PLATFORM}")

IF(CMAKE_BUILD_TYPE STREQUAL "Debug")
    MESSAGE("-- Debug Mode")
    SET(GLOBAL_BUILD_MODE "Debug")
ELSEIF(CMAKE_BUILD_TYPE STREQUAL "Release")
    MESSAGE("-- Release Mode")
    SET(GLOBAL_BUILD_MODE "Release")
ELSEIF(CMAKE_BUILD_TYPE STREQUAL "RelWithDebInfo")
    MESSAGE("-- RelWithDebInfo Mode")
    SET(GLOBAL_BUILD_MODE "RelWithDebInfo")
ELSE()
    MESSAGE("-- Build mode default to Release")
    MESSAGE("-- Release Mode")
    SET(GLOBAL_BUILD_MODE "Release")
ENDIF()

IF(NOT PACKAGE)
	SET(PACKAGE "packagename_invalid")
	MESSAGE(FATAL_ERROR "Invalid package name")
ENDIF()

IF(NOT PACKAGE_VERSION)
	SET(PACKAGE_VERSION "verson_invalid")
	MESSAGE(FATAL_ERROR "Invalid version in package")
ENDIF()

IF(NOT LIBRARY_TYPE)
	SET(LIBRARY_TYPE "STATIC")
ENDIF()

SET(PACKAGE "${PACKAGE}" CACHE STRING "Package to compile")
SET(PACKAGE_VERSION "${PACKAGE_VERSION}" CACHE STRING "Version to compile")

option_combobox(GLOBAL_PLATFORM "win32;win64;linux_amd64;solaris_sparc32" "${GLOBAL_PLATFORM}" "Platform")
option_combobox(CMAKE_BUILD_TYPE "Debug;Release;RelWithDebInfo" "${GLOBAL_BUILD_MODE}" "Build type")

SET(CMAKE_VERBOSE_MAKEFILE ON)
IF(NOT DEFINED GTC_INSTALL_PREFIX)
	SET(GTC_INSTALL_PREFIX "${CMAKE_SOURCE_DIR}/../${PACKAGE}-${PACKAGE_VERSION}-${GLOBAL_PLATFORM}/${PACKAGE}-${PACKAGE_VERSION}")
	SET(CMAKE_INSTALL_PREFIX "${GTC_INSTALL_PREFIX}/${GLOBAL_PLATFORM}/${GLOBAL_COMPILER}/${GLOBAL_BUILD_MODE}")

	IF(WIN32)
		SET(EXECUTABLE_OUTPUT_PATH "${GTC_INSTALL_PREFIX}/${GLOBAL_PLATFORM}/${GLOBAL_COMPILER}" CACHE PATH "Folder executables")
		SET(LIBRARY_OUTPUT_PATH "${GTC_INSTALL_PREFIX}/${GLOBAL_PLATFORM}/${GLOBAL_COMPILER}" CACHE PATH "Folder libs")
	ELSE()
		SET(EXECUTABLE_OUTPUT_PATH "${GTC_INSTALL_PREFIX}/${GLOBAL_PLATFORM}/${GLOBAL_COMPILER}/${GLOBAL_BUILD_MODE}" CACHE PATH "Folder executables")
		SET(LIBRARY_OUTPUT_PATH "${GTC_INSTALL_PREFIX}/${GLOBAL_PLATFORM}/${GLOBAL_COMPILER}/${GLOBAL_BUILD_MODE}" CACHE PATH "Folder libs")
	ENDIF()
ELSE()
	SET(GTC_INSTALL_PREFIX "${GTC_INSTALL_PREFIX}")
	SET(CMAKE_INSTALL_PREFIX "${GTC_INSTALL_PREFIX}")
	SET(EXECUTABLE_OUTPUT_PATH "${GTC_INSTALL_PREFIX}/bin" CACHE PATH "Folder executables")
	SET(LIBRARY_OUTPUT_PATH "${GTC_INSTALL_PREFIX}/lib" CACHE PATH "Folder libs")
ENDIF()

LINK_DIRECTORIES(${LIBRARY_OUTPUT_PATH})


# Copyright (c) 2011 David Love
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

##
## Project Definition
##

# Project Name
project ( shiny )

# Set-up CMake
cmake_minimum_required ( VERSION 2.6 )

# Include the checks for library functions
include ( CheckLibraryExists )

# Include the checks for header files
include ( CheckIncludeFiles )

# Include the checks for type symbols
include ( CheckTypeSize ) 

# Include the checks for functions
include ( cmake/extra/CheckPrototypeDefinition.cmake ) 

##
## Compiler Configuration
##

# Microsoft compilers
if ( MSVC OR MSVC_IDE OR MSVC60 OR MSVC70 OR MSVC71 OR MSVC80 OR CMAKE_COMPILER_2005 OR MSVC90 OR MSVC10 )
	# Define the export symbols
	set ( SHINY_INLINE inline )
	set ( SHINY_UNUSED  )
	set ( SHINY_EXPORT __declspec\(dllexport\) )
	
	# Define the standard integer types
	if ( CYGWIN )
		set ( UINT32_T	u_int32_t 		 	 )
		set ( UINT64_T 	u_int64_t 			 )
	else ( CYGWIN )
		set ( INT32_T 	int					 		 )
		set ( UINT32_T	unsigned int 		 )
		set ( INT64_T		__int64			 		 )
		set ( UINT64_T 	unsigned __int64 )
	endif ( CYGWIN )
endif ( MSVC OR MSVC_IDE OR MSVC60 OR MSVC70 OR MSVC71 OR MSVC80 OR CMAKE_COMPILER_2005 OR MSVC90 OR MSVC10 )

# GNU Compiler
if ( ${CMAKE_COMPILER_IS_GNUCC} ) 
  message ( "-- Using GCC compiler profile...")

	set ( SHINY_INLINE __inline__ )
	set ( SHINY_UNUSED __attribute__\(\(unused\)\) )
	set ( SHINY_EXPORT __attribute__\(\(dllexport\)\) )
endif ( ${CMAKE_COMPILER_IS_GNUCC} ) 

# Check for CLang (this should be redundant eventually, as a patch
# has been made to the 2.8 branch. However, until that version becomes
# common, this will do)
#
# NOTE: This MUST be done AFTER the GCC check, as Clang also shows up
# as GCC. So test for that first, then Clang. One day this will all go
# away..
if ( "${CMAKE_C_COMPILER_ID}" MATCHES "Clang" )
  message ( "-- Using Clang compiler profile...")

endif ( "${CMAKE_C_COMPILER_ID}" MATCHES "Clang" )

##
## Project Configuration
##

# Add the global configure file to the search path
include_directories( ${CMAKE_CURRENT_SOURCE_DIR}/lib/config )

##
## Header File Configuration
##

# Look for the "assert.h" header file
check_include_files ( assert.h HAVE_ASSERT_H )

# Look for the "inttypes.h" header file
check_include_files ( inttypes.h HAVE_INTTYPES_H )

# Look for the "stdint.h" header file
check_include_files ( stdint.h HAVE_STDINT_H )

# Look for the header files defining the constants for type lengths
check_include_files ( values.h HAVE_VALUES_H )
check_include_files ( float.h HAVE_FLOAT_H )
check_include_files ( limits.h HAVE_LIMITS_H )

# Look for a separate malloc header
check_include_files ( malloc.h EXPLICIT_MALLOC_H )

##
## Library Configuration
##

# Look for the math library: on some platforms this is part of the C
# library, on others it needs linking separately
check_library_exists ( m floor "" SEPARATE_LIB_M ) 

if ( SEPARATE_LIB_M )
  # If the math library is separate, then it needs to be included
  # in the global link flags
  set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -lm")
  set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -lm")
  set(CMAKE_MODULE_LINKER_FLAGS "${CMAKE_MODULE_LINKER_FLAGS} -lm")
endif( SEPARATE_LIB_M )

# Work out where timeval lives
set ( CMAKE_EXTRA_INCLUDE_FILES sys/resource.h )
	check_type_size( "struct timeval" TIME_IN_SYS_RESOURCE )
set ( CMAKE_EXTRA_INCLUDE_FILES )

set ( CMAKE_EXTRA_INCLUDE_FILES sys/time.h )
	check_type_size( "struct timeval" TIME_IN_SYS_TIME )
set ( CMAKE_EXTRA_INCLUDE_FILES )

# Work out where gettimeofday lives
check_prototype_definition ( gettimeofday "int gettimeofday(struct timeval *restrict tp, void *restrict tzp)" "NULL" "sys/time.h" GETTIMEOFDAY_IN_SYS_TIME ) 
check_prototype_definition ( gettimeofday "int gettimeofday(struct timeval *restrict tp, void *restrict tzp)" "NULL" "time.h" GETTIMEOFDAY_IN_TIME )

##
## Platform Configuration
##

# Look for the main platform types

if ( UNIX )
	set ( PLATFORM_TYPE 0x02 )
	message ( "UNIX" )
endif ( UNIX )

if ( WIN32 )
	set ( PLATFORM_TYPE 0x01 )
endif ( WIN32 )

# Check whether we are on a 32-bit or a 64-bit platform for non-Apple
# platforms: Apple platforms have to be checked at compile time

if ( NOT APPLE )
#   # check 64 bit
#   if ( CMAKE_SIZEOF_VOID_P EQUALS 4 )
#     set ( HAVE_64_BIT 0 )
#   else ( CMAKE_SIZEOF_VOID_P EQUALS 4 )
#     set ( HAVE_64_BIT 1 )
#   endif ( CMAKE_SIZEOF_VOID_P EQUALS 4 )
   set ( HAVE_64_BIT 1 )

   # check endianness
   include ( TestBigEndian )
   test_big_endian ( HAVE_BIG_ENDIAN )
   if ( HAVE_BIG_ENDIAN )
     set ( HAVE_BIG_ENDIAN 1 )
   else ( HAVE_BIG_ENDIAN )
     set ( HAVE_BIG_ENDIAN 0 )
   endif ( HAVE_BIG_ENDIAN )
endif ( NOT APPLE )

##
## Core Configuration File
##

# Set the global configure file
configure_file ( ${CMAKE_CURRENT_SOURCE_DIR}/lib/config/config_cmake.h.in ${CMAKE_CURRENT_SOURCE_DIR}/lib/config/config_cmake.h )

##
## C Library Sources
##

# Add the Shiny header files to the search path
include_directories ( ${CMAKE_CURRENT_SOURCE_DIR}/trunk/Shiny/include )

add_library ( shiny
	trunk/Shiny/src/ShinyManager.c
	trunk/Shiny/src/ShinyNode.c
	trunk/Shiny/src/ShinyNodePool.c
	trunk/Shiny/src/ShinyNodeState.c
	trunk/Shiny/src/ShinyOutput.c
	trunk/Shiny/src/ShinyTools.c
	trunk/Shiny/src/ShinyZone.c 
	)
	
##

#link_directories (${CMAKE_CURRENT_SOURCE_DIR}) 

add_executable ( shiny-simple 
	trunk/Samples/Simple/Simple.cpp
	)
	
target_link_libraries (shiny-simple shiny) 

