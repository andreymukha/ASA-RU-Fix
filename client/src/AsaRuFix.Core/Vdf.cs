using System.Text;

namespace AsaRuFix.Core;

/// <summary>Reads KeyValues while keeping source spans for narrowly scoped edits.</summary>
public sealed class VdfDocument
{
    private readonly string source;
    private readonly VdfEntry root;

    private VdfDocument(string source, VdfEntry root) { this.source = source; this.root = root; }

    public static VdfDocument Parse(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        return new VdfDocument(text, new Parser(text).Read());
    }

    public string? Get(params string[] path)
    {
        var entry = Locate(path);
        if (entry is { Children: not null }) throw new FormatException("Ожидалось строковое значение VDF.");
        return entry?.Value;
    }

    internal IReadOnlyList<VdfEntry> Children(params string[] path) => Locate(path)?.Children ?? [];

    public string Set(string[] path, string value)
    {
        ArgumentNullException.ThrowIfNull(value);
        ValidatePath(path);
        var parent = root;
        for (int i = 0; i < path.Length; i++)
        {
            var existing = Child(parent, path[i]);
            if (existing is null)
            {
                string newline = source.Contains("\r\n", StringComparison.Ordinal) ? "\r\n" : "\n";
                var content = new StringBuilder();
                for (int j = i; j < path.Length - 1; j++)
                    content.Append(newline).Append('\t', j + 1).Append(Encode(path[j])).Append(newline).Append('\t', j + 1).Append('{');
                content.Append(newline).Append('\t', path.Length).Append(Encode(path[^1])).Append('\t').Append(Encode(value));
                for (int j = path.Length - 2; j >= i; j--) content.Append(newline).Append('\t', j + 1).Append('}');
                content.Append(newline).Append('\t', i);
                return source.Insert(parent.ClosePosition, content.ToString());
            }
            if (i == path.Length - 1)
            {
                if (existing.Children is not null) throw new FormatException("Нельзя заменить объект VDF строкой.");
                return source[..existing.ValueStart] + Encode(value) + source[existing.ValueEnd..];
            }
            if (existing.Children is null) throw new FormatException("Родитель VDF должен быть объектом.");
            parent = existing;
        }
        throw new InvalidOperationException();
    }

    internal string Remove(string[] path)
    {
        var entry = Locate(path);
        if (entry is null) return source;
        if (entry.Children is not null) throw new FormatException("Удаляемый ключ VDF должен содержать строку.");
        return source[..entry.Start] + source[entry.End..];
    }

    private VdfEntry? Locate(string[] path)
    {
        ValidatePath(path);
        VdfEntry? entry = root;
        foreach (var key in path)
        {
            if (entry is null) return null;
            if (entry.Children is null) throw new FormatException("Родитель VDF должен быть объектом.");
            entry = Child(entry, key);
        }
        return entry;
    }

    private static void ValidatePath(string[] path)
    {
        ArgumentNullException.ThrowIfNull(path);
        if (path.Length == 0 || path.Any(string.IsNullOrEmpty)) throw new ArgumentException("Нужен непустой путь VDF.", nameof(path));
    }

    private static VdfEntry? Child(VdfEntry parent, string key)
    {
        var matches = parent.Children!.Where(x => x.Key.Equals(key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (matches.Length > 1) throw new FormatException($"Неоднозначный ключ VDF: {key}.");
        return matches.FirstOrDefault();
    }

    private static string Encode(string value) => "\"" + value.Replace("\\", "\\\\", StringComparison.Ordinal)
        .Replace("\"", "\\\"", StringComparison.Ordinal).Replace("\n", "\\n", StringComparison.Ordinal)
        .Replace("\r", "\\r", StringComparison.Ordinal).Replace("\t", "\\t", StringComparison.Ordinal) + "\"";

    internal sealed record VdfEntry(string Key, string? Value, List<VdfEntry>? Children, int Start, int End, int ValueStart, int ValueEnd, int ClosePosition);

    private sealed class Parser(string text)
    {
        private int position;
        public VdfEntry Read()
        {
            var children = Entries(false, 0, out _);
            return new VdfEntry("", null, children, 0, text.Length, 0, 0, text.Length);
        }

        private List<VdfEntry> Entries(bool nested, int depth, out int close)
        {
            if (depth > 128) throw new FormatException("Слишком глубокая вложенность VDF.");
            var entries = new List<VdfEntry>();
            while (true)
            {
                SkipTrivia();
                if (position == text.Length)
                {
                    if (nested) throw new FormatException("Незакрытый объект VDF.");
                    close = position;
                    return entries;
                }
                if (text[position] == '}')
                {
                    if (!nested) throw new FormatException("Лишняя закрывающая скобка VDF.");
                    close = position++;
                    return entries;
                }
                int start = position;
                string key = Token();
                SkipTrivia();
                if (position < text.Length && text[position] == '{')
                {
                    position++;
                    var children = Entries(true, depth + 1, out int end);
                    entries.Add(new VdfEntry(key, null, children, start, position, 0, 0, end));
                }
                else
                {
                    int valueStart = position;
                    string value = Token();
                    entries.Add(new VdfEntry(key, value, null, start, position, valueStart, position, 0));
                }
            }
        }

        private string Token()
        {
            if (position >= text.Length || text[position] is '{' or '}') throw new FormatException("Отсутствует ключ или значение VDF.");
            if (text[position] != '"')
            {
                int start = position;
                while (position < text.Length && !char.IsWhiteSpace(text[position]) && text[position] is not '{' and not '}' and not '"') position++;
                if (position == start) throw new FormatException("Некорректный токен VDF.");
                return text[start..position];
            }
            position++;
            var result = new StringBuilder();
            while (position < text.Length)
            {
                char c = text[position++];
                if (c == '"') return result.ToString();
                if (c == '\\')
                {
                    if (position == text.Length) throw new FormatException("Незакрытая строка VDF.");
                    char escaped = text[position++];
                    switch (escaped)
                    {
                        case '"': result.Append('"'); break;
                        case '\\': result.Append('\\'); break;
                        case 'n': result.Append('\n'); break;
                        case 'r': result.Append('\r'); break;
                        case 't': result.Append('\t'); break;
                        default: result.Append('\\').Append(escaped); break;
                    }
                }
                else result.Append(c);
            }
            throw new FormatException("Незакрытая строка VDF.");
        }

        private void SkipTrivia()
        {
            while (position < text.Length)
            {
                if (char.IsWhiteSpace(text[position]) || position == 0 && text[position] == '\uFEFF') { position++; continue; }
                if (position + 1 < text.Length && text[position] == '/' && text[position + 1] == '/')
                {
                    position += 2;
                    while (position < text.Length && text[position] is not '\r' and not '\n') position++;
                    continue;
                }
                if (position + 1 < text.Length && text[position] == '/' && text[position + 1] == '*')
                {
                    int end = text.IndexOf("*/", position + 2, StringComparison.Ordinal);
                    if (end < 0) throw new FormatException("Незакрытый комментарий VDF.");
                    position = end + 2;
                    continue;
                }
                break;
            }
        }
    }
}
