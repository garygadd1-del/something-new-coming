//! Immune wrapper for a masked brain.
//!
//! Valid JSON prints `OK` and exits 0.
//! Anything sideways prints `REROUTE` and exits 2, before the bad mask is used.
//! This crate has no dependencies so it builds offline once `rustc` is present.

use std::env;
use std::fs;
use std::io::{self, Read};
use std::process::ExitCode;

const MAX_BYTES: usize = 1_048_576;
const MAX_DEPTH: usize = 16;
const SCHEMA: &str = "agios.metal_master.masked_brain.v1";

#[derive(Debug)]
enum Value {
    Null,
    Bool(bool),
    Number(f64),
    String(String),
    Array(Vec<Value>),
    Object(Vec<(String, Value)>),
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => {
            println!("OK");
            ExitCode::from(0)
        }
        Err(reason) => {
            println!("REROUTE");
            eprintln!("{reason}");
            ExitCode::from(2)
        }
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let path = args
        .next()
        .ok_or_else(|| "usage: mask_guard <masked-brain.json>".to_string())?;
    if args.next().is_some() {
        return Err("usage: mask_guard <masked-brain.json>".to_string());
    }
    let raw = if path == "-" {
        let mut buf = String::new();
        io::stdin()
            .read_to_string(&mut buf)
            .map_err(|err| format!("cannot read stdin: {err}"))?;
        buf
    } else {
        fs::read_to_string(&path).map_err(|err| format!("cannot read mask json: {err}"))?
    };
    validate_json(&raw)
}

fn validate_json(raw: &str) -> Result<(), String> {
    if raw.len() > MAX_BYTES {
        return Err("mask json is too large".to_string());
    }
    let value = parse_json(raw.as_bytes())?;
    validate_value(&value)
}

fn validate_value(value: &Value) -> Result<(), String> {
    let pairs = match value {
        Value::Object(pairs) => pairs,
        _ => return Err("masked brain must be an object".to_string()),
    };
    let mut seen_schema = false;
    let mut seen_role = false;
    let mut seen_parameters = false;
    for (key, child) in pairs {
        match key.as_str() {
            "schema" => {
                seen_schema = true;
                match child {
                    Value::String(text) if text == SCHEMA => {}
                    _ => return Err("schema is not a masked brain".to_string()),
                }
            }
            "brain_id" => {
                let text = expect_string(child, "brain_id")?;
                if !is_slug(text) {
                    return Err("brain_id is not a slug".to_string());
                }
            }
            "role" => {
                seen_role = true;
                let text = expect_string(child, "role")?;
                if !is_slug(text) {
                    return Err("role is not a slug".to_string());
                }
            }
            "job" => match child {
                Value::Null => {}
                Value::String(text) if is_slug(text) => {}
                _ => return Err("job must be a slug or null".to_string()),
            },
            "emergent" => {
                if as_bool(child).is_none() {
                    return Err("emergent must be a boolean".to_string());
                }
            }
            "jobs" | "stripped" => expect_slug_array(child, key)?,
            "parameters" => {
                seen_parameters = true;
                expect_parameters(child)?;
            }
            _ => return Err(format!("unknown field {key}")),
        }
    }
    if !seen_schema || !seen_role || !seen_parameters {
        return Err("masked brain is missing schema, role, or parameters".to_string());
    }
    Ok(())
}

fn expect_parameters(value: &Value) -> Result<(), String> {
    let pairs = match value {
        Value::Object(pairs) if !pairs.is_empty() => pairs,
        Value::Object(_) => return Err("parameters empty".to_string()),
        _ => return Err("parameters must be an object".to_string()),
    };
    for (key, child) in pairs {
        if !is_slug(key) {
            return Err(format!("parameter {key} is not a slug"));
        }
        match child {
            Value::Object(inner) if !inner.is_empty() => {}
            Value::Object(_) => return Err(format!("parameter {key} is empty")),
            _ => return Err(format!("parameter {key} must be an object")),
        }
        walk(child, 0)?;
    }
    Ok(())
}

fn expect_slug_array(value: &Value, label: &str) -> Result<(), String> {
    let items = match value {
        Value::Array(items) => items,
        _ => return Err(format!("{label} must be an array")),
    };
    for item in items {
        match item {
            Value::String(text) if is_slug(text) => {}
            _ => return Err(format!("{label} entry is not a slug")),
        }
    }
    Ok(())
}

fn as_bool(value: &Value) -> Option<bool> {
    match value {
        Value::Bool(flag) => Some(*flag),
        _ => None,
    }
}

fn expect_string<'a>(value: &'a Value, label: &str) -> Result<&'a str, String> {
    match value {
        Value::String(text) => Ok(text),
        _ => Err(format!("{label} must be a string")),
    }
}

fn walk(value: &Value, depth: usize) -> Result<(), String> {
    if depth > MAX_DEPTH {
        return Err("nesting too deep".to_string());
    }
    match value {
        Value::Object(pairs) => {
            for (key, child) in pairs {
                if !is_key(key) {
                    return Err(format!("bad key {key}"));
                }
                match key.as_str() {
                    "doctrine" => match child {
                        Value::String(text) if text == "defense_only" => {}
                        _ => return Err("doctrine must be defense_only".to_string()),
                    },
                    "leader_voice" => match child {
                        Value::String(text) if text == "when_called" => {}
                        _ => return Err("leader_voice must be when_called".to_string()),
                    },
                    "enabled" => {
                        if as_bool(child).is_none() {
                            return Err("enabled must be a boolean".to_string());
                        }
                    }
                    "scope" => match child {
                        Value::String(text) if text == "house" || text == "house_only" || text == "lane" => {}
                        _ => return Err("scope is not a house scope".to_string()),
                    },
                    _ => {}
                }
                walk(child, depth + 1)?;
            }
        }
        Value::Array(items) => {
            for item in items {
                walk(item, depth + 1)?;
            }
        }
        Value::Number(number) => {
            if !number.is_finite() {
                return Err("non-finite number".to_string());
            }
        }
        Value::Null | Value::Bool(_) | Value::String(_) => {}
    }
    Ok(())
}

fn is_slug(text: &str) -> bool {
    let bytes = text.as_bytes();
    if bytes.is_empty() || bytes.len() > 64 {
        return false;
    }
    if !bytes[0].is_ascii_lowercase() {
        return false;
    }
    bytes
        .iter()
        .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || *byte == b'_')
}

fn is_key(text: &str) -> bool {
    let bytes = text.as_bytes();
    if bytes.is_empty() || bytes.len() > 64 {
        return false;
    }
    let first = bytes[0];
    if !(first.is_ascii_alphabetic() || first == b'_') {
        return false;
    }
    bytes
        .iter()
        .all(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
}

fn parse_json(bytes: &[u8]) -> Result<Value, String> {
    if bytes.len() > MAX_BYTES {
        return Err("mask json is too large".to_string());
    }
    let start = skip_ws(bytes, 0);
    if start >= bytes.len() {
        return Err("mask json is empty".to_string());
    }
    let (value, next) = parse_value(bytes, start, 0)?;
    let end = skip_ws(bytes, next);
    if end != bytes.len() {
        return Err(format!("byte {end}: trailing junk"));
    }
    Ok(value)
}

fn parse_value(bytes: &[u8], index: usize, depth: usize) -> Result<(Value, usize), String> {
    if index >= bytes.len() {
        return Err(format!("byte {index}: unexpected end"));
    }
    match bytes[index] {
        b'n' => parse_lit(bytes, index, b"null", Value::Null),
        b't' => parse_lit(bytes, index, b"true", Value::Bool(true)),
        b'f' => parse_lit(bytes, index, b"false", Value::Bool(false)),
        b'"' => {
            let (text, next) = parse_string(bytes, index)?;
            Ok((Value::String(text), next))
        }
        b'[' => parse_array(bytes, index, depth),
        b'{' => parse_object(bytes, index, depth),
        b'-' | b'0'..=b'9' => {
            let (number, next) = parse_number(bytes, index)?;
            Ok((Value::Number(number), next))
        }
        _ => Err(format!("byte {index}: unexpected character")),
    }
}

fn parse_lit(bytes: &[u8], index: usize, literal: &[u8], value: Value) -> Result<(Value, usize), String> {
    let end = index + literal.len();
    if end > bytes.len() || &bytes[index..end] != literal {
        return Err(format!("byte {index}: bad literal"));
    }
    Ok((value, end))
}

fn parse_array(bytes: &[u8], index: usize, depth: usize) -> Result<(Value, usize), String> {
    if depth + 1 > MAX_DEPTH {
        return Err("nesting too deep".to_string());
    }
    let mut cursor = skip_ws(bytes, index + 1);
    let mut items = Vec::new();
    if cursor < bytes.len() && bytes[cursor] == b']' {
        return Ok((Value::Array(items), cursor + 1));
    }
    loop {
        let (value, next) = parse_value(bytes, cursor, depth + 1)?;
        items.push(value);
        cursor = skip_ws(bytes, next);
        if cursor >= bytes.len() {
            return Err("unterminated array".to_string());
        }
        if bytes[cursor] == b']' {
            return Ok((Value::Array(items), cursor + 1));
        }
        if bytes[cursor] != b',' {
            return Err(format!("byte {cursor}: expected comma"));
        }
        cursor = skip_ws(bytes, cursor + 1);
        if cursor < bytes.len() && bytes[cursor] == b']' {
            return Err("trailing comma".to_string());
        }
    }
}

fn parse_object(bytes: &[u8], index: usize, depth: usize) -> Result<(Value, usize), String> {
    if depth + 1 > MAX_DEPTH {
        return Err("nesting too deep".to_string());
    }
    let mut cursor = skip_ws(bytes, index + 1);
    let mut pairs = Vec::new();
    if cursor < bytes.len() && bytes[cursor] == b'}' {
        return Ok((Value::Object(pairs), cursor + 1));
    }
    loop {
        if cursor >= bytes.len() || bytes[cursor] != b'"' {
            return Err(format!("byte {cursor}: object key must be a string"));
        }
        let (key, after_key) = parse_string(bytes, cursor)?;
        if pairs.iter().any(|(existing, _)| existing == &key) {
            return Err(format!("duplicate key {key}"));
        }
        cursor = skip_ws(bytes, after_key);
        if cursor >= bytes.len() || bytes[cursor] != b':' {
            return Err(format!("byte {cursor}: expected colon"));
        }
        cursor = skip_ws(bytes, cursor + 1);
        let (value, next) = parse_value(bytes, cursor, depth + 1)?;
        pairs.push((key, value));
        cursor = skip_ws(bytes, next);
        if cursor >= bytes.len() {
            return Err("unterminated object".to_string());
        }
        if bytes[cursor] == b'}' {
            return Ok((Value::Object(pairs), cursor + 1));
        }
        if bytes[cursor] != b',' {
            return Err(format!("byte {cursor}: expected comma"));
        }
        cursor = skip_ws(bytes, cursor + 1);
        if cursor < bytes.len() && bytes[cursor] == b'}' {
            return Err("trailing comma".to_string());
        }
    }
}

fn parse_string(bytes: &[u8], index: usize) -> Result<(String, usize), String> {
    if bytes.get(index) != Some(&b'"') {
        return Err(format!("byte {index}: expected string"));
    }
    let mut cursor = index + 1;
    let mut out = String::new();
    while cursor < bytes.len() {
        let byte = bytes[cursor];
        if byte == b'"' {
            return Ok((out, cursor + 1));
        }
        if byte < 0x20 {
            return Err(format!("byte {cursor}: raw control in string"));
        }
        if byte == b'\\' {
            cursor += 1;
            if cursor >= bytes.len() {
                return Err("unterminated escape".to_string());
            }
            match bytes[cursor] {
                b'"' => out.push('"'),
                b'\\' => out.push('\\'),
                b'/' => out.push('/'),
                b'b' => out.push('\u{0008}'),
                b'f' => out.push('\u{000c}'),
                b'n' => out.push('\n'),
                b'r' => out.push('\r'),
                b't' => out.push('\t'),
                b'u' => {
                    let (character, next) = parse_unicode(bytes, cursor + 1)?;
                    out.push(character);
                    cursor = next;
                    continue;
                }
                _ => return Err(format!("byte {cursor}: bad escape")),
            }
            cursor += 1;
            continue;
        }
        let rest = std::str::from_utf8(&bytes[cursor..])
            .map_err(|_| format!("byte {cursor}: bad utf-8"))?;
        let character = rest
            .chars()
            .next()
            .ok_or_else(|| format!("byte {cursor}: bad utf-8"))?;
        out.push(character);
        cursor += character.len_utf8();
    }
    Err("unterminated string".to_string())
}

fn parse_unicode(bytes: &[u8], index: usize) -> Result<(char, usize), String> {
    let (unit, next) = hex4(bytes, index)?;
    if (0xD800..=0xDBFF).contains(&unit) {
        if next + 1 >= bytes.len() || bytes[next] != b'\\' || bytes[next + 1] != b'u' {
            return Err("lone surrogate".to_string());
        }
        let (low, after) = hex4(bytes, next + 2)?;
        if !(0xDC00..=0xDFFF).contains(&low) {
            return Err("bad surrogate pair".to_string());
        }
        let point = 0x10000 + (((unit - 0xD800) << 10) | (low - 0xDC00));
        let character = char::from_u32(point).ok_or_else(|| "bad unicode scalar".to_string())?;
        return Ok((character, after));
    }
    if (0xDC00..=0xDFFF).contains(&unit) {
        return Err("lone surrogate".to_string());
    }
    let character = char::from_u32(unit).ok_or_else(|| "bad unicode scalar".to_string())?;
    Ok((character, next))
}

fn hex4(bytes: &[u8], index: usize) -> Result<(u32, usize), String> {
    if index + 4 > bytes.len() {
        return Err("short unicode escape".to_string());
    }
    let text = std::str::from_utf8(&bytes[index..index + 4])
        .map_err(|_| "bad unicode escape".to_string())?;
    let value = u32::from_str_radix(text, 16).map_err(|_| "bad unicode escape".to_string())?;
    Ok((value, index + 4))
}

fn parse_number(bytes: &[u8], index: usize) -> Result<(f64, usize), String> {
    let start = index;
    let mut cursor = index;
    if cursor < bytes.len() && bytes[cursor] == b'-' {
        cursor += 1;
    }
    if cursor >= bytes.len() {
        return Err(format!("byte {index}: bad number"));
    }
    if bytes[cursor] == b'0' {
        cursor += 1;
    } else if bytes[cursor].is_ascii_digit() {
        while cursor < bytes.len() && bytes[cursor].is_ascii_digit() {
            cursor += 1;
        }
    } else {
        return Err(format!("byte {index}: bad number"));
    }
    if cursor < bytes.len() && bytes[cursor] == b'.' {
        cursor += 1;
        let fraction = cursor;
        while cursor < bytes.len() && bytes[cursor].is_ascii_digit() {
            cursor += 1;
        }
        if cursor == fraction {
            return Err(format!("byte {index}: bad number"));
        }
    }
    if cursor < bytes.len() && (bytes[cursor] == b'e' || bytes[cursor] == b'E') {
        cursor += 1;
        if cursor < bytes.len() && (bytes[cursor] == b'+' || bytes[cursor] == b'-') {
            cursor += 1;
        }
        let exponent = cursor;
        while cursor < bytes.len() && bytes[cursor].is_ascii_digit() {
            cursor += 1;
        }
        if cursor == exponent {
            return Err(format!("byte {index}: bad number"));
        }
    }
    let text = std::str::from_utf8(&bytes[start..cursor]).map_err(|_| "bad number".to_string())?;
    let number: f64 = text.parse().map_err(|_| format!("bad number {text}"))?;
    if !number.is_finite() {
        return Err("non-finite number".to_string());
    }
    Ok((number, cursor))
}

fn skip_ws(bytes: &[u8], mut index: usize) -> usize {
    while index < bytes.len() && matches!(bytes[index], b' ' | b'\n' | b'\r' | b'\t') {
        index += 1;
    }
    index
}

#[cfg(test)]
mod tests {
    use super::validate_json;

    fn librarian() -> String {
        r#"{"schema":"agios.metal_master.masked_brain.v1","role":"librarian","parameters":{"catalog":{"enabled":true}}}"#
            .to_string()
    }

    #[test]
    fn accepts_a_little_mask() {
        validate_json(&librarian()).unwrap();
    }

    #[test]
    fn reroutes_raid_doctrine() {
        let raw = r#"{"schema":"agios.metal_master.masked_brain.v1","role":"warrior","parameters":{"combat":{"enabled":true,"doctrine":"raid"}}}"#;
        let err = validate_json(raw).unwrap_err();
        assert!(err.contains("defense_only"), "{err}");
    }

    #[test]
    fn reroutes_leader_voice() {
        let raw = r#"{"schema":"agios.metal_master.masked_brain.v1","role":"mayor","parameters":{"speech":{"enabled":true,"leader_voice":"always"}}}"#;
        let err = validate_json(raw).unwrap_err();
        assert!(err.contains("when_called"), "{err}");
    }

    #[test]
    fn reroutes_empty_parameters() {
        let raw = r#"{"schema":"agios.metal_master.masked_brain.v1","role":"librarian","parameters":{}}"#;
        assert!(validate_json(raw).unwrap_err().contains("empty"));
    }

    #[test]
    fn reroutes_unknown_field() {
        let raw = r#"{"schema":"agios.metal_master.masked_brain.v1","role":"librarian","exec":"rm","parameters":{"catalog":{"enabled":true}}}"#;
        assert!(validate_json(raw).unwrap_err().contains("unknown field"));
    }

    #[test]
    fn reroutes_duplicate_key() {
        let raw = r#"{"schema":"agios.metal_master.masked_brain.v1","schema":"agios.metal_master.masked_brain.v1","role":"librarian","parameters":{"catalog":{"enabled":true}}}"#;
        assert!(validate_json(raw).unwrap_err().contains("duplicate"));
    }

    #[test]
    fn reroutes_trailing_junk_and_leading_zero() {
        assert!(validate_json("{\"a\":1} true").is_err());
        assert!(validate_json("01").is_err());
        assert!(validate_json("").is_err());
    }

    #[test]
    fn reroutes_non_finite_and_deep_nesting() {
        assert!(validate_json("1e309").unwrap_err().contains("non-finite") || validate_json("1e309").is_err());
        let mut raw = String::new();
        for _ in 0..20 {
            raw.push_str("{\"a\":");
        }
        raw.push('1');
        for _ in 0..20 {
            raw.push('}');
        }
        assert!(validate_json(&raw).unwrap_err().contains("deep"));
    }

    #[test]
    fn reroutes_enabled_string_and_raw_control() {
        let raw = r#"{"schema":"agios.metal_master.masked_brain.v1","role":"librarian","parameters":{"catalog":{"enabled":"yes"}}}"#;
        assert!(validate_json(raw).unwrap_err().contains("boolean"));
        assert!(validate_json("{\"a\":\"line\nb\"}").is_err());
    }
}
