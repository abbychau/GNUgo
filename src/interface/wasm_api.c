/* WebAssembly entry points for GNU Go.
 *
 * Exposes the engine to JavaScript through the Go Text Protocol:
 *
 *   gnugo_wasm_init(seed, memory_mb)  -> 1 on success
 *   gnugo_wasm_gtp(command_line)      -> full GTP response string
 *                                        ("= ...\n\n" or "? ...\n\n")
 *
 * The returned string stays valid until the next gnugo_wasm_gtp() call.
 */

#include "gnugo.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "liberty.h"
#include "interface.h"
#include "gtp.h"

#ifdef __EMSCRIPTEN__
#include <emscripten/emscripten.h>
#else
#define EMSCRIPTEN_KEEPALIVE
#endif

static int initialized = 0;
static char *response = NULL;
static size_t response_len = 0;

EMSCRIPTEN_KEEPALIVE int
gnugo_wasm_init(unsigned int seed, float memory)
{
  if (initialized)
    return 1;

  /* memory < 0 lets the engine pick its default cache size. */
  init_gnugo(memory, seed);
  play_gtp_init(stdout, 0);
  initialized = 1;
  return 1;
}

EMSCRIPTEN_KEEPALIVE const char *
gnugo_wasm_gtp(const char *command)
{
  char line[GTP_BUFSIZE];
  FILE *out;

  if (!initialized)
    gnugo_wasm_init(0, -1.0);

  free(response);
  response = NULL;
  response_len = 0;

  out = open_memstream(&response, &response_len);
  if (!out)
    return "? out of memory\n\n";

  strncpy(line, command, GTP_BUFSIZE - 2);
  line[GTP_BUFSIZE - 2] = '\0';
  if (!strchr(line, '\n'))
    strcat(line, "\n");

  gtp_output_file = out;
  play_gtp_execute(line);
  fclose(out);
  gtp_output_file = stdout;

  return response ? response : "";
}
