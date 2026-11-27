/*
 * Metal Master Fort — shift-job scheduler.
 *
 * Minutes depend on role and the bot's current goal. A rendering goal gives
 * game_dev a thermal-scheduled slot inside Gary's standing caps (2026-11-25):
 * Throne RX 7900 XTX 86C core / 88C hotspot / 80% load,
 * SelfAware RX 9070 85C core, SelfAware GTX 1650 80C core.
 * Hotspot and load on the 9070 and the 1650 are OPEN.
 * Fuzzy 66 has only the RX 7900 GRE. Its ceiling is OPEN.
 *
 * The planted swarm list is selfaware and fuzzy66 only. Throne may appear
 * on a thermal line. A bot line may not name Throne.
 * This program reads a local text file. It does not open a socket.
 *
 *   thermal throne rx_7900_xtx <core_c> <hotspot_c> <load_pct>
 *   thermal selfaware rx_9070 <core_c>
 *   thermal selfaware gtx_1650 <core_c>
 *   bot <id> <role> <goal> <host>
 *   seat <blank-id> <minutes>
 *
 * A thermal line may tighten a standing cap. It may not loosen one.
 * A refused thermal line leaves the previous ceiling in place.
 * A fuzzy66 thermal line is refused because the GRE ceiling is OPEN.
 * A seat line assigns minutes to a blank job id. It has no name field.
 * BLANK_MINUTES_CAP is an EXAMPLE until the owner sets a blank-seat budget.
 *
 * stdout is OK lines, REROUTE lines, then SUMMARY.
 * exit 0: all OK. exit 2: nothing scheduled, or usage. exit 3: mixed.
 */

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define THRONE_CORE_C 86
#define THRONE_HOTSPOT_C 88
#define THRONE_LOAD_PCT 80
#define CORE_9070_C 85
#define CORE_1650_C 80
/* EXAMPLE until the owner sets a blank-seat minute cap.
   45 is the longest role slot already assigned in this file. */
#define BLANK_MINUTES_CAP 45

#define MAX_LINE 512
#define MAX_TOK 8

static int g_9070_core = CORE_9070_C;
static int g_1650_core = CORE_1650_C;
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
            if (write_note(note, note_len, "rx9070_core%d_gtx1650_core%d", g_9070_core, g_1650_core) != 0) {
                return -1;
            }
            return 40;
        }
        if (strcmp(host, "fuzzy66") != 0) {
            return -1;
        }
        if (copy_text(window, window_len, "thermal_fuzzy66") != 0) {
            return -1;
        }
        if (copy_text(note, note_len, "rx7900gre_ceiling_open") != 0) {
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

static int blank_id(const char *text)
{
    size_t index;
    size_t length;

    if (text == NULL || strncmp(text, "blank.", 6) != 0) {
        return 0;
    }
    length = strlen(text);
    if (length < 7 || length > 9) {
        return 0;
    }
    for (index = 6; index < length; index++) {
        if (!isdigit((unsigned char)text[index])) {
            return 0;
        }
    }
    return 1;
}

static int parse_minutes(const char *text, int *out)
{
    char *end = NULL;
    long value;

    if (text == NULL || !isdigit((unsigned char)text[0])) {
        return -1;
    }
    errno = 0;
    value = strtol(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0') {
        return -1;
    }
    if (value < 1 || value > BLANK_MINUTES_CAP) {
        return -1;
    }
    *out = (int)value;
    return 0;
}

static void apply_seat(char **tok, int count)
{
    int minutes = 0;

    if (count > 3) {
        reroute("blank seat names stay blank");
        return;
    }
    if (count != 3 || !blank_id(tok[1])) {
        reroute("blank seat line refused");
        return;
    }
    if (parse_minutes(tok[2], &minutes) != 0) {
        reroute("blank seat minutes refused");
        return;
    }
    printf("OK seat=%s minutes=%d name=\n", tok[1], minutes);
    g_ok++;
}

static void apply_thermal(char **tok, int count)
{
    int core = 0;
    int hot = 0;
    int load = 0;

    if (count < 3 || !slugish(tok[1]) || !slugish(tok[2])) {
        reroute("thermal line refused");
        return;
    }
    if (strcmp(tok[1], "fuzzy66") == 0) {
        reroute("fuzzy66 RX 7900 GRE ceiling is OPEN");
        return;
    }
    if (strcmp(tok[1], "throne") == 0 && strcmp(tok[2], "rx_7900_xtx") == 0) {
        if (count != 6) {
            reroute("thermal line refused");
            return;
        }
        if (parse_temp(tok[3], THRONE_CORE_C, &core) != 0
            || parse_temp(tok[4], THRONE_HOTSPOT_C, &hot) != 0
            || parse_temp(tok[5], THRONE_LOAD_PCT, &load) != 0) {
            reroute("thermal ceiling cannot loosen the house line");
            return;
        }
        (void)core;
        (void)hot;
        (void)load;
        return;
    }
    if (strcmp(tok[1], "selfaware") == 0 && strcmp(tok[2], "rx_9070") == 0) {
        if (count != 4) {
            reroute(count > 4 ? "hotspot is OPEN" : "thermal line refused");
            return;
        }
        if (parse_temp(tok[3], CORE_9070_C, &core) != 0) {
            reroute("thermal ceiling cannot loosen the house line");
            return;
        }
        g_9070_core = core;
        return;
    }
    if (strcmp(tok[1], "selfaware") == 0 && strcmp(tok[2], "gtx_1650") == 0) {
        if (count != 4) {
            reroute(count > 4 ? "hotspot is OPEN" : "thermal line refused");
            return;
        }
        if (parse_temp(tok[3], CORE_1650_C, &core) != 0) {
            reroute("thermal ceiling cannot loosen the house line");
            return;
        }
        g_1650_core = core;
        return;
    }
    reroute("thermal host is outside the standing caps");
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
    if (strcmp(tok[0], "seat") == 0) {
        apply_seat(tok, count);
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
