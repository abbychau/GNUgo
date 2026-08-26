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
