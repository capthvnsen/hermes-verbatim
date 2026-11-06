# Verbatim

Hermes will round $14.99 into $15, drop a character from an email, and slide a deadline by a day. Asking it not to is a prompt. Verbatim is a gate.

You state an exact value. Verbatim pins it. A later file write, shell command, or final reply that swaps in a near-miss is blocked before it lands. The wrong reply is held, so you never see the rounded number flash by.

This is not a memory plugin and not a "did you finish" checker. Those can still paraphrase. Verbatim checks the bytes.

## Install

```bash
hermes plugins install /path/to/verbatim
hermes plugins enable verbatim
```

Restart the gateway. New sessions pick it up.

Kill switch, no restart: `VERBATIM_DISABLE=1` or `/verbatim off`.

## What gets pinned

Only a short message (800 characters or less), and only when you actually state a constraint:

- `the price is exactly $14.99`
- `exactly $14.99` or `must stay $14.99`
- `email is ada@example.com`
- `the deadline is 2026-11-11`
- `never say synergy`

A pasted page does not become a pile of pins. `/verbatim pin ...` pins from a longer note when you mean it.

Saying the price again replaces that pin. It does not stack a second copy.

## What it blocks

On `write_file`, `patch`, `terminal`, `execute_code`, and `skill_manage`, a near-miss is refused and the tool result tells the agent the exact value. A final reply with a near-miss is replaced, before you see it, with a short hold notice.

Near-miss means:

- money rounded to the next dollar (`$14.99` vs `$15`), truncated (`$14.9`), or within 2%
- an email one or two characters off
- a deadline one character off (`2026-11-11` vs `2026-11-12`)
- a banned word, whole word only

A different price (`$100`) is left alone. A sentence that also contains the exact pinned value is left alone, so "not $15, use $14.99" passes.

Lookups (`web_search`, `read_file`) are not scanned.

## Commands

```text
/verbatim
/verbatim pin the price is exactly $14.99
/verbatim drop price
/verbatim check Only $15/month
/verbatim off
/verbatim on
```

Tools, if the agent needs them: `verbatim_pin`, `verbatim_list`, `verbatim_drop`, `verbatim_check`.

## Demo (under 90 seconds)

1. Enable the plugin and start a fresh chat.
2. Say: `The price is exactly $14.99 a month. Write pricing.md with that price.`
3. If the model writes `$15`, the write is blocked and the reply is held. The notice names `$14.99`.
4. The retry writes `$14.99`. Show the file.
5. `/verbatim` shows the pin id.

That is the whole product. The block is the feature.

## Disclosure

- Reads the user message each turn to detect a constraint. Stores the exact string, a short quote, and a label in the profile's `plugin-data/verbatim/pins.json`. No network. No credentials. No telemetry.
- Scans arguments of mutating tools and the final assistant reply. Does not scan lookups.
- Can block a tool call and replace a final reply. Internal errors fail open: the agent keeps working, and the miss is logged.
- Pins persist across sessions until you drop them. Cap is 40.
Holding is on while the plugin is enabled. Every reply is checked before you see it, then delivered whole. A clean reply is unchanged. A conflicting reply is replaced with the hold notice, so the rounded number never streams past you. `/verbatim off` stops the checks. Streaming comes back when you disable the plugin, because the hold is registered at load.

## Catalog

Not a skin of constraint-vault (that plugin injects the string and does not check obedience) and not a skin of proofgate (that plugin checks completion claims against tool evidence). Verbatim checks the draft against the exact value you stated.

Admission notes for the catalog PR:

- Surfaces: `pre_llm_call` (inject), `pre_tool_call` (block), `transform_llm_output` with `hold_stream` (hold the reply), four tools, `/verbatim`.
- No core override, no desktop patching, no self-updater, no third-party network.
- Validate with `hermes plugins validate /path/to/verbatim --install-deps` before opening the PR.
