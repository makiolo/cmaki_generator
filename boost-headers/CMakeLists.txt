cmake_minimum_required(VERSION 2.8)
cmake_policy(SET CMP0011 NEW)

IF(NOT DEFINED BASENAME_STRIP)
	MESSAGE(FATAL_ERROR "Undefined $BASENAME_STRIP (example: boost_1_XX_0)")
ENDIF()

# http://www.boost.org/doc/libs/1_65_0/more/getting_started/windows.html

include(${PACKAGE_BUILD_DIRECTORY}/../boost-headers/find.cmake)

IF(CMAKE_BUILD_TYPE STREQUAL "Debug")
    set(MODE debug)
ELSEIF(CMAKE_BUILD_TYPE STREQUAL "Release")
    set(MODE release)
ELSEIF(CMAKE_BUILD_TYPE STREQUAL "RelWithDebInfo")
    set(MODE release)
ELSE()
    MESSAGE(FATAL_ERROR "Error detecting build mode")
ENDIF()

if(CMAKE_SYSTEM_NAME MATCHES Linux)
	set(ARCH 64)
	set(ARCH_NAME x86)
elseif(CMAKE_SYSTEM_NAME MATCHES SunOS)
	set(ARCH 32)
	set(ARCH_NAME x86)
elseif(CMAKE_SYSTEM_NAME MATCHES Windows)
	if(CMAKE_CL_64)
		set(ARCH 64)
		set(ARCH_NAME x86)
	else(CMAKE_CL_64)
		set(ARCH 32)
		set(ARCH_NAME x86)
	endif(CMAKE_CL_64)
endif()

IF(WIN32)
	set(PROGRAM_B2 "b2.exe")
	set(PROGRAM_BOOTSTRAP "bootstrap.bat")
	set(TOOLSET "msvc")
	set(INSTALL_DIR "${LIBRARY_OUTPUT_PATH}/${GLOBAL_BUILD_MODE}")
ELSE()
	set(PROGRAM_B2 "./b2")
	set(PROGRAM_BOOTSTRAP "bootstrap.sh")
	if ("${CMAKE_CXX_COMPILER_ID}" STREQUAL "Clang")
		set(TOOLSET "clang")
	else() # if ("${CMAKE_CXX_COMPILER_ID}" STREQUAL "GNU")
		set(TOOLSET "gcc")
	endif()
	set(INSTALL_DIR "${LIBRARY_OUTPUT_PATH}")
ENDIF()

IF(CMAKE_BUILD_TYPE STREQUAL "Debug")
	set(EXTRA_DEBUG "runtime-debugging=on")
ELSE()
	set(EXTRA_DEBUG "runtime-debugging=off")
ENDIF()

set(BOOST_TOP_WORKING_DIR ${boost_headers_BUILD})
set(BOOST_WORKING_DIR "${boost_headers_BUILD}/${BASENAME_STRIP}")
set(BOOST_INTERMEDIATE_DIR "${boost_headers_BUILD}/${BASENAME_STRIP}/build")

MESSAGE("-- writing ${BOOST_WORKING_DIR}/tools/build/v2/user-config.jam")

if ("${CMAKE_CXX_COMPILER_ID}" STREQUAL "Clang")
	# using Clang
	FILE(WRITE "${BOOST_WORKING_DIR}/usr.jam"
	"import option ;\n"
	"using clang : : $ENV{CXX} : <cxxflags>$ENV{CXXFLAGS} ;\n")
elseif ("${CMAKE_CXX_COMPILER_ID}" STREQUAL "GNU")
	# using GCC
	FILE(WRITE "${BOOST_WORKING_DIR}/usr.jam"
	"import option ;\n"
	"using gcc : : $ENV{CXX} : <cxxflags>$ENV{CXXFLAGS} ;\n")
endif()

IF(BOOST_INSTALL_HEADERS EQUAL 1)

	if(NOT WIN32)

		# execute_process(
		# 					COMMAND "patch" "-N" "-p0" "--strip=1"
		# 					INPUT_FILE "${BOOST_TOP_WORKING_DIR}/fix_1_58.patch"
		# 					WORKING_DIRECTORY ${BOOST_WORKING_DIR})
		# execute_process(
		# 					COMMAND "patch" "-N" "-p0" "--strip=1"
		# 					INPUT_FILE "${BOOST_TOP_WORKING_DIR}/fix_1_58b.patch"
		# 					WORKING_DIRECTORY ${BOOST_WORKING_DIR})
		execute_process(
							COMMAND "chmod" "+x" "${PROGRAM_BOOTSTRAP}"
							WORKING_DIRECTORY ${BOOST_WORKING_DIR})
		execute_process(
							COMMAND "sh" "${PROGRAM_BOOTSTRAP}" "--without-icu"
							WORKING_DIRECTORY ${BOOST_WORKING_DIR})
		execute_process(
							COMMAND "chmod" "+x" "${PROGRAM_B2}"
							WORKING_DIRECTORY ${BOOST_WORKING_DIR})

	else()
		# execute_process(
		# 					COMMAND "patch" "-N" "-p0" "--strip=0"
		# 					INPUT_FILE "${BOOST_TOP_WORKING_DIR}/vector_of_vector.patch"
		# 					WORKING_DIRECTORY ${BOOST_WORKING_DIR}/boost/numeric/ublas)
		execute_process(
							COMMAND "${PROGRAM_BOOTSTRAP}"
							WORKING_DIRECTORY ${BOOST_WORKING_DIR})
	endif()

	INSTALL(DIRECTORY "${BOOST_WORKING_DIR}/boost" DESTINATION include)

ELSE()

	IF(BOOST_PARAMETERS STREQUAL "--with-python")

		IF(CMAKE_BUILD_TYPE STREQUAL "Debug")
			include(${PACKAGE_BUILD_DIRECTORY}/../python/find.cmake)
			set(PYTHON_DEBUG "python-debugging=on")
			file( TO_CMAKE_PATH ${python_LIBDIR} PYTHON_BASE )
			file( TO_CMAKE_PATH ${python_INCLUDE}/python3.5m PYTHON_INCL )
			file( TO_CMAKE_PATH ${python_LIBDIR}/lib PYTHON_LIBS )
		ELSE()
			include(${PACKAGE_BUILD_DIRECTORY}/../python/find.cmake)
			set(PYTHON_DEBUG)
			file( TO_CMAKE_PATH ${python_LIBDIR} PYTHON_BASE )
			file( TO_CMAKE_PATH ${python_INCLUDE}/python3.5m PYTHON_INCL )
			file( TO_CMAKE_PATH ${python_LIBDIR}/lib PYTHON_LIBS )
		ENDIF()

		if ("${CMAKE_CXX_COMPILER_ID}" STREQUAL "Clang")
			set(PYTHON_USING "clang")
		elseif ("${CMAKE_CXX_COMPILER_ID}" STREQUAL "GNU")
			set(PYTHON_USING "gcc")
		else()
			set(PYTHON_USING "msvc")
		endif()

		FILE(WRITE "${BOOST_WORKING_DIR}/project-config.jam"
"import option ;\n"
"using ${PYTHON_USING} ;\n"
"option.set keep-going : false ;\n"
"using python : 3.5 : ${PYTHON_BASE} : ${PYTHON_INCL} : ${PYTHON_LIBS} ;\n"
		)

	ELSE()
		set(PYTHON_DEBUG)
	ENDIF()

	IF(WIN32)
		execute_process(COMMAND "${PROGRAM_B2}" "--build-dir=${BOOST_INTERMEDIATE_DIR}" "--stagedir=${INSTALL_DIR}" "--toolset=${TOOLSET}" "architecture=${ARCH_NAME}" "address-model=${ARCH}" "link=shared" "${EXTRA_DEBUG}" "${PYTHON_DEBUG}" "variant=${MODE}" "--disable-icu" "--layout=versioned" "stage" "-a" "${BOOST_PARAMETERS}" WORKING_DIRECTORY ${BOOST_WORKING_DIR})
	ELSE()
		execute_process(COMMAND "${PROGRAM_B2}" "--build-dir=${BOOST_INTERMEDIATE_DIR}" "--stagedir=${INSTALL_DIR}" "--toolset=${TOOLSET}" "address-model=${ARCH}" "link=shared" "${EXTRA_DEBUG}" "${PYTHON_DEBUG}" "variant=${MODE}" "--disable-icu" "--layout=versioned" "stage" "-a" "${BOOST_PARAMETERS}" WORKING_DIRECTORY ${BOOST_WORKING_DIR})
	ENDIF()
ENDIF()

# need install any file
file(TO_CMAKE_PATH "${BOOST_WORKING_DIR}/LICENSE_1_0.txt" LICENSE_FILE)
INSTALL(FILES "${LICENSE_FILE}" DESTINATION share)

