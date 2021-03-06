PROJECT(UNITEST_CMAKI_GENERATOR_${CMAKI_PLATFORM}_${CMAKE_BUILD_TYPE} CXX)
cmake_minimum_required(VERSION 3.0)

# include("$ENV{CMAKI_PWD}/node_modules/cmaki/cmaki.cmake")
include(cmaki)

get_filename_component(BASEDIR "${CMAKE_CURRENT_LIST_FILE}" PATH)
set(CMAKE_INSTALL_PREFIX ${CMAKE_CURRENT_BINARY_DIR})
set(EXECUTABLE_OUTPUT_PATH "${CMAKE_INSTALL_PREFIX}")
set(LIBRARY_OUTPUT_PATH "${CMAKE_INSTALL_PREFIX}")

foreach(PACKAGE_ITER ${FIND_PACKAGES})
	string(TOUPPER ${PACKAGE_ITER} PACKAGE_UPPER)
	string(REGEX REPLACE "-" "_" PACKAGE_UPPER ${PACKAGE_UPPER})
	message("find_package in test: ${PACKAGE_UPPER}")
	include("${DEPENDS_PATH}/3rdpartyversions/${PACKAGE_ITER}.cmake")
	cmaki_find_package(${PACKAGE_ITER} ${${PACKAGE_UPPER}_REQUIRED_VERSION})
endforeach()
message("include dirs: ${CMAKI_INCLUDE_DIRS}")
message("libs to link in test: ${CMAKI_LIBRARIES}")

foreach(INCLUDE_DIR ${CMAKI_INCLUDE_DIRS})
	include_directories(${INCLUDE_DIR})
endforeach()
add_executable(test_${CMAKI_PLATFORM} ${UNITTEST_PATH})
target_link_libraries(test_${CMAKI_PLATFORM} ${CMAKI_LIBRARIES})
install(TARGETS test_${CMAKI_PLATFORM} DESTINATION "${CMAKE_INSTALL_PREFIX}/${CMAKE_BUILD_TYPE}")

enable_testing()
add_test(NAME test_cmake_${CMAKI_PLATFORM} COMMAND test_${CMAKI_PLATFORM} WORKING_DIRECTORY "${CMAKE_INSTALL_PREFIX}/${CMAKE_BUILD_TYPE}")

