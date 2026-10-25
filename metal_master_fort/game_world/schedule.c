/*
 * Metal Master Fort — scheduling stub.
 *
 * Minutes depend on role and the bot's current goal. A rendering goal gives
 * game_dev a thermal-scheduled slot. SelfAware stays inside Gary's RX 7900 XTX
 * line (80C core / 88C hotspot). Fuzzy 66 stays on the RX 6600 cheap-pass lane
 * (fort default 70C core / 80C hotspot).
 *
 * The swarm is selfaware and fuzzy66 only.
 * This program reads a local text file. It does not open a socket.
 *
 *   thermal <host> <core_c> <hotspot_c> <lane>
 *   bot <id> <role> <goal> <host>
 *
 * A thermal line may tighten a ceiling. It may not loosen one.
 * A refused thermal line leaves the previous ceiling in place.
 *
 * stdout is OK lines, REROUTE lines, then SUMMARY.
 * exit 0: all OK. exit 2: nothing scheduled, or usage. exit 3: mixed.
 */

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define XTX_CORE_C 80
#define XTX_HOTSPOT_C 88
#define FUZZY_CORE_C 70
#define FUZZY_HOTSPOT_C 80

#define MAX_LINE 512
#define MAX_TOK 8

static int g_self_core = XTX_CORE_C;
static int g_self_hot = XTX_HOTSPOT_C;
static int g_fuzzy_core = FUZZY_CORE_C;
static int g_fuzzy_hot = FUZZY_HOTSPOT_C;
static int g_ok = 0;
static int g_reroute = 0;

static void reroute(const char *msg)
{
    printf("REROUTE %s\n", msg);
    g_reroute++;
}

static int slugish(const char *text)
{
    size_t index;
    size_t length;

    if (text == NULL || text[0] == '\0') {
        return 0;
    }
    length = strlen(text);
    if (length > 64) {
        return 0;
    }
    if (!isalpha((unsigned char)text[0])) {
        return 0;
    }
    for (index = 1; index < length; index++) {
        unsigned char character = (unsigned char)text[index];
        if (!isalnum(character) && character != '_' && character != '-') {
            return 0;
        }
    }
    return 1;
}

static int parse_temp(const char *text, int ceiling, int *out)
{
    char *end = NULL;
    long value;

    errno = 0;
    value = strtol(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0') {
        return -1;
    }
    if (value < 1 || value > ceiling) {
        return -1;
    }
    *out = (int)value;
    return 0;
}

static int split_line(char *line, char **tok, int max_tokens)
{
    int count = 0;
    char *cursor = line;

    while (*cursor != '\0') {
        while (*cursor == ' ' || *cursor == '\t' || *cursor == '\r') {
            cursor++;
        }
        if (*cursor == '\0' || *cursor == '#') {
            break;
        }
        if (count >= max_tokens) {
            return -1;
        }
        tok[count++] = cursor;
        while (*cursor != '\0' && *cursor != ' ' && *cursor != '\t'
               && *cursor != '\r' && *cursor != '#') {
            cursor++;
        }
        if (*cursor == '#') {
            *cursor = '\0';
            break;
        }
        if (*cursor != '\0') {
            *cursor = '\0';
            cursor++;
        }
    }
    return count;
}

static int copy_text(char *dest, size_t dest_len, const char *text)
{
    size_t length = strlen(text);
    if (length + 1 > dest_len) {
        return -1;
    }
    memcpy(dest, text, length + 1);
    return 0;
}

static int write_note(char *dest, size_t dest_len, const char *fmt, int left, int right)
{
    int wrote = snprintf(dest, dest_len, fmt, left, right);
    if (wrote < 0 || (size_t)wrote >= dest_len) {
        return -1;
    }
    return 0;
}

static int minutes_for(
    const char *role,
    const char *goal,
    const char *host,
    char *window,
    size_t window_len,
    char *note,
    size_t note_len)
{
    if (strcmp(goal, "rendering") == 0) {
        if (strcmp(role, "game_dev") != 0) {
            return -1;
        }
        if (strcmp(host, "selfaware") == 0) {
            if (copy_text(window, window_len, "thermal_selfaware") != 0) {
                return -1;
            }
            if (write_note(note, note_len, "rx7900xtx_core%d_hotspot%d", g_self_core, g_self_hot) != 0) {
                return -1;
            }
            return 40;
        }
        if (copy_text(window, window_len, "cheap_pass") != 0) {
            return -1;
        }
        if (write_note(note, note_len, "rx6600_cheap_pass_core%d_hotspot%d", g_fuzzy_core, g_fuzzy_hot) != 0) {
            return -1;
        }
        return 20;
    }

    if (strcmp(role, "game_dev") == 0) {
        if (copy_text(window, window_len, "game_dev_idle") != 0 || copy_text(note, note_len, "no_render_goal") != 0) {
            return -1;
        }
        return 25;
    }
    if (strcmp(role, "mayor") == 0) {
        if (copy_text(window, window_len, "civic") != 0 || copy_text(note, note_len, "steady") != 0) {
            return -1;
        }
        return 30;
    }
    if (strcmp(role, "warrior") == 0) {
        if (copy_text(window, window_len, "watch") != 0 || copy_text(note, note_len, "steady") != 0) {
            return -1;
        }
        return 20;
    }
    if (strcmp(role, "tailor") == 0 || strcmp(role, "metals") == 0) {
        if (copy_text(window, window_len, "craft") != 0 || copy_text(note, note_len, "steady") != 0) {
            return -1;
        }
        return 35;
    }
    if (strcmp(role, "wood_getter") == 0 || strcmp(role, "stone_getter") == 0
        || strcmp(role, "mineral_getter") == 0) {
        if (copy_text(window, window_len, "field") != 0 || copy_text(note, note_len, "steady") != 0) {
            return -1;
        }
        return 45;
    }
    if (strcmp(role, "sulfur_getter") == 0) {
        if (copy_text(window, window_len, "field") != 0 || copy_text(note, note_len, "steady") != 0) {
            return -1;
        }
        return 40;
    }
    if (strcmp(role, "book_librarian") == 0) {
        if (copy_text(window, window_len, "library") != 0 || copy_text(note, note_len, "steady") != 0) {
            return -1;
        }
        return 30;
    }
    if (strcmp(role, "caravan_master") == 0) {
        if (copy_text(window, window_len, "road") != 0 || copy_text(note, note_len, "steady") != 0) {
            return -1;
        }
        return 35;
    }
    if (strcmp(role, "marketer") == 0) {
        if (copy_text(window, window_len, "market") != 0 || copy_text(note, note_len, "steady") != 0) {
            return -1;
        }
        return 25;
    }
    if (copy_text(window, window_len, "general") != 0 || copy_text(note, note_len, "unlisted_role") != 0) {
        return -1;
    }
    return 15;
}

static void apply_thermal(char **tok, int count)
{
    int core = 0;
    int hot = 0;
    int ceiling_core;
    int ceiling_hot;

    if (count != 5 || !slugish(tok[1]) || !slugish(tok[4])) {
        reroute("thermal line refused");
        return;
    }
    if (strcmp(tok[1], "selfaware") == 0) {
        ceiling_core = XTX_CORE_C;
        ceiling_hot = XTX_HOTSPOT_C;
        if (strcmp(tok[4], "primary") != 0) {
            reroute("selfaware lane must be primary");
            return;
        }
    } else if (strcmp(tok[1], "fuzzy66") == 0) {
        ceiling_core = FUZZY_CORE_C;
        ceiling_hot = FUZZY_HOTSPOT_C;
        if (strcmp(tok[4], "cheap_pass") != 0) {
            reroute("fuzzy66 lane must be cheap_pass");
            return;
        }
    } else {
        reroute("thermal host is outside the swarm");
        return;
    }
    if (parse_temp(tok[2], ceiling_core, &core) != 0
        || parse_temp(tok[3], ceiling_hot, &hot) != 0) {
        reroute("thermal ceiling cannot loosen the house line");
        return;
    }
    if (strcmp(tok[1], "selfaware") == 0) {
        g_self_core = core;
        g_self_hot = hot;
    } else {
        g_fuzzy_core = core;
        g_fuzzy_hot = hot;
    }
}

static void apply_bot(char **tok, int count)
{
    char window[64];
    char note[96];
    int minutes;

    if (count != 5 || !slugish(tok[1]) || !slugish(tok[2]) || !slugish(tok[3]) || !slugish(tok[4])) {
        reroute("bot line refused");
        return;
    }
    if (strcmp(tok[4], "selfaware") != 0 && strcmp(tok[4], "fuzzy66") != 0) {
        reroute("bot host is outside the swarm");
        return;
    }
    minutes = minutes_for(tok[2], tok[3], tok[4], window, sizeof window, note, sizeof note);
    if (minutes < 0) {
        reroute("rendering slots are game_dev only");
        return;
    }
    printf(
        "OK bot=%s role=%s goal=%s host=%s minutes=%d window=%s note=%s\n",
        tok[1], tok[2], tok[3], tok[4], minutes, window, note);
    g_ok++;
}

static void handle_line(char *line)
{
    char *tok[MAX_TOK];
    int count = split_line(line, tok, MAX_TOK);

    if (count == 0) {
        return;
    }
    if (count < 0) {
        reroute("too many tokens");
        return;
    }
    if (strcmp(tok[0], "thermal") == 0) {
        apply_thermal(tok, count);
        return;
    }
    if (strcmp(tok[0], "bot") == 0) {
        apply_bot(tok, count);
        return;
    }
    reroute("unknown command");
}

static int finish(void)
{
    printf("SUMMARY ok=%d reroute=%d\n", g_ok, g_reroute);
    if (g_reroute == 0) {
        return 0;
    }
    if (g_ok == 0) {
        return 2;
    }
    return 3;
}

static int read_stream(FILE *in)
{
    char buf[MAX_LINE];

    while (fgets(buf, (int)sizeof buf, in) != NULL) {
        size_t length = strlen(buf);
        if (length > 0 && buf[length - 1] != '\n' && !feof(in)) {
            reroute("line too long");
            return finish();
        }
        if (length > 0 && buf[length - 1] == '\n') {
            buf[length - 1] = '\0';
        }
        handle_line(buf);
    }
    if (ferror(in)) {
        reroute("read failed");
        return finish();
    }
    return finish();
}

int main(int argc, char **argv)
{
    FILE *in;
    int code;

    if (argc > 2) {
        fprintf(stderr, "usage: schedule [goals.txt]\n");
        return 2;
    }
    if (argc == 2) {
        in = fopen(argv[1], "r");
        if (in == NULL) {
            reroute("cannot open goals file");
            return finish();
        }
        code = read_stream(in);
        fclose(in);
        return code;
    }
    return read_stream(stdin);
}
