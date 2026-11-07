INCLUDE_DIRECTORIES(${GNUGo_SOURCE_DIR}/src/engine)
INCLUDE_DIRECTORIES(${GNUGo_SOURCE_DIR}/src/sgf)
INCLUDE_DIRECTORIES(${GNUGo_SOURCE_DIR}/src/utils)

########### gnugo executable ###############

SET(gnugo_SRCS
    main.c
    play_ascii.c
    play_gmp.c
    play_gtp.c
    play_solo.c
    play_test.c
    gmp.c
    gtp.c
    )

ADD_EXECUTABLE(gnugo ${gnugo_SRCS})

IF(WIN32)
    SET(PLATFORM_LIBRARIES wsock32)
ENDIF(WIN32)

IF(UNIX)
    SET(PLATFORM_LIBRARIES m)
ENDIF(UNIX)

TARGET_LINK_LIBRARIES(gnugo sgf engine sgf utils patterns ${PLATFORM_LIBRARIES})

INSTALL(TARGETS gnugo DESTINATION bin)

########### WebAssembly module (Emscripten only) ###############
#
# Produces gnugo-core.js + gnugo-core.wasm, a MODULARIZE build exposing
# the factory `createGnuGoModule()`. After linking, the engine and the
# browser files from wasm/ (worker, JS API, demo page) are collected in
# ${CMAKE_BINARY_DIR}/web, ready to be served as static files.

IF(EMSCRIPTEN)
    TARGET_LINK_OPTIONS(gnugo PRIVATE -sNODERAWFS=1 -sEXIT_RUNTIME=1 -sALLOW_MEMORY_GROWTH=1
                                      -sSTACK_SIZE=4MB)

    ADD_EXECUTABLE(gnugo_wasm wasm_api.c play_gtp.c gtp.c)
    SET_TARGET_PROPERTIES(gnugo_wasm PROPERTIES OUTPUT_NAME gnugo-core)
    TARGET_LINK_LIBRARIES(gnugo_wasm sgf engine sgf utils patterns)
    TARGET_LINK_OPTIONS(gnugo_wasm PRIVATE
        -sMODULARIZE=1
        -sEXPORT_NAME=createGnuGoModule
        -sENVIRONMENT=web,worker,node
        -sALLOW_MEMORY_GROWTH=1
        -sINITIAL_MEMORY=64MB
        -sSTACK_SIZE=4MB
        -sFILESYSTEM=0
        "-sEXPORTED_FUNCTIONS=['_gnugo_wasm_init','_gnugo_wasm_gtp','_malloc','_free']"
        "-sEXPORTED_RUNTIME_METHODS=['ccall','cwrap','UTF8ToString']"
        )

    SET(GNUGO_WEB_DIR ${CMAKE_BINARY_DIR}/web)
    SET(GNUGO_WEB_SRC ${GNUGo_SOURCE_DIR}/wasm)
    ADD_CUSTOM_COMMAND(TARGET gnugo_wasm POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E make_directory ${GNUGO_WEB_DIR}
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_FILE_DIR:gnugo_wasm>/gnugo-core.js
                $<TARGET_FILE_DIR:gnugo_wasm>/gnugo-core.wasm
                ${GNUGO_WEB_SRC}/gnugo.js
                ${GNUGO_WEB_SRC}/gnugo-worker.js
                ${GNUGO_WEB_SRC}/index.html
                ${GNUGO_WEB_DIR}
        COMMENT "Collecting web files in ${GNUGO_WEB_DIR}"
        )
ENDIF(EMSCRIPTEN)
