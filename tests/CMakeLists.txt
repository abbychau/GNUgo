# Regression tests, run with
#
#     ctest --test-dir build -j8                # native, single-config
#     ctest --test-dir build -C Release -j8     # Visual Studio
#
# Each key suite is one test. It fails on any hard failure, an engine
# crash, or fewer passes / more known failures than baseline.json.
# Keep KEY_SUITES in sync with KEY_SUITES in run_tests.py.

FIND_PACKAGE(Python3 COMPONENTS Interpreter)
IF(NOT Python3_Interpreter_FOUND)
    MESSAGE(STATUS "Python 3 not found: regression tests disabled")
    RETURN()
ENDIF()

SET(KEY_SUITES
    tiny tactics reading atari_atari owl connect semeai endgame capture
    13x13 strategy)

FOREACH(suite ${KEY_SUITES})
    ADD_TEST(NAME regress.${suite}
             COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/run_tests.py
                     $<TARGET_FILE:gnugo> --strict --baseline ${suite}.tst)
    SET_TESTS_PROPERTIES(regress.${suite} PROPERTIES LABELS regress TIMEOUT 1800)
ENDFOREACH()

# The WebAssembly module: GTP, genmove and SGF through the in-memory
# file system, loaded the way the browser worker loads it.
IF(EMSCRIPTEN AND CMAKE_CROSSCOMPILING_EMULATOR)
    ADD_TEST(NAME wasm.smoke
             COMMAND ${CMAKE_CROSSCOMPILING_EMULATOR}
                     ${CMAKE_CURRENT_SOURCE_DIR}/tools/wasm_smoke.cjs
                     ${CMAKE_BINARY_DIR}/web/gnugo-core.js)
    SET_TESTS_PROPERTIES(wasm.smoke PROPERTIES LABELS smoke)
ENDIF()
