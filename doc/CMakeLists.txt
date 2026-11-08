# The man page is installed with the program. The Texinfo manual is
# built on request:
#
#     cmake --build build --target manual
#
# which writes build/manual/index.html (one page per node) and
# build/doc/gnugo.info. Needs makeinfo (package "texinfo").

INSTALL(FILES gnugo.6 DESTINATION ${CMAKE_INSTALL_MANDIR}/man6)

FIND_PROGRAM(MAKEINFO_EXECUTABLE NAMES makeinfo texi2any)
IF(NOT MAKEINFO_EXECUTABLE)
    RETURN()
ENDIF()

SET(MANUAL_HTML_DIR ${CMAKE_BINARY_DIR}/manual)
FILE(GLOB MANUAL_SOURCES ${CMAKE_CURRENT_SOURCE_DIR}/*.texi)
FILE(GLOB MANUAL_IMAGES ${CMAKE_CURRENT_SOURCE_DIR}/*.png
                        ${CMAKE_CURRENT_SOURCE_DIR}/*.jpg)

ADD_CUSTOM_COMMAND(
    OUTPUT ${MANUAL_HTML_DIR}/index.html
    COMMAND ${MAKEINFO_EXECUTABLE} --html --output=${MANUAL_HTML_DIR}
            ${CMAKE_CURRENT_SOURCE_DIR}/gnugo.texi
    COMMAND ${CMAKE_COMMAND} -E copy_if_different ${MANUAL_IMAGES} ${MANUAL_HTML_DIR}
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    DEPENDS ${MANUAL_SOURCES} ${MANUAL_IMAGES}
    COMMENT "Building the HTML manual in ${MANUAL_HTML_DIR}")

ADD_CUSTOM_COMMAND(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/gnugo.info
    COMMAND ${MAKEINFO_EXECUTABLE} --output=${CMAKE_CURRENT_BINARY_DIR}/gnugo.info
            ${CMAKE_CURRENT_SOURCE_DIR}/gnugo.texi
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    DEPENDS ${MANUAL_SOURCES}
    COMMENT "Building the Info manual")

ADD_CUSTOM_TARGET(manual
    DEPENDS ${MANUAL_HTML_DIR}/index.html ${CMAKE_CURRENT_BINARY_DIR}/gnugo.info)
