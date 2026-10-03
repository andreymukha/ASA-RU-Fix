using System.Text;

namespace AsaRuFix.Core;

public sealed record CommandSpec(string FileName, string Arguments);
public static class GameCommandBuilder
{
    public static string Quote(string value)
    {
        ArgumentNullException.ThrowIfNull(value);
        if (value.Contains('\0')) throw new ArgumentException("Аргумент содержит NUL.", nameof(value));
        var quoted = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') quoted.Append('\\', slashes * 2 + 1).Append(c);
            else quoted.Append('\\', slashes).Append(c);
            slashes = 0;
        }
        return quoted.Append('\\', slashes * 2).Append('"').ToString();
    }

    public static string[] Parse(string command) => Tokens(command, false).Select(x => x.Value).ToArray();

    public static void ValidateOriginal(string original)
    {
        ArgumentNullException.ThrowIfNull(original);
        if (original.IndexOfAny(['\0', '\r', '\n', '&', '|', '<', '>', '^', '`', ';', '$']) >= 0)
            throw new ArgumentException("Обнаружены сложные параметры запуска Steam.", nameof(original));
        var tokens = Tokens(original, true);
        var templates = tokens.Where(x => x.Value.Contains("%command%", StringComparison.OrdinalIgnoreCase)).ToArray();
        if (templates.Length == 0)
        {
            if (original.Contains('%')) throw new ArgumentException("Переменные окружения не поддерживаются.", nameof(original));
            return;
        }
        if (templates.Length != 1 || original[templates[0].Start..templates[0].End] != "%command%")
            throw new ArgumentException("Нужен один самостоятельный %command% без кавычек.", nameof(original));
        if ((original[..templates[0].Start] + original[templates[0].End..]).Contains('%'))
            throw new ArgumentException("Переменные окружения не поддерживаются.", nameof(original));
        if (tokens[0] != templates[0]) ValidateExecutable(tokens[0].Value);
    }

    public static CommandSpec Build(IReadOnlyList<string> gameArgs, string original)
    {
        ArgumentNullException.ThrowIfNull(gameArgs);
        if (gameArgs.Count == 0) throw new ArgumentException("Исходная команда игры отсутствует.", nameof(gameArgs));
        ValidateExecutable(gameArgs[0]);
        ValidateOriginal(original);
        var originalTokens = Tokens(original, true);
        var template = originalTokens.SingleOrDefault(x => x.Value == "%command%");
        if (template is null)
        {
            string arguments = string.Join(" ", gameArgs.Skip(1).Select(Quote));
            if (original.Length > 0) arguments += " " + original;
            return new CommandSpec(gameArgs[0], arguments);
        }
        string gameCommand = string.Join(" ", gameArgs.Select(Quote));
        string expanded = original[..template.Start] + gameCommand + original[template.End..];
        var first = Tokens(expanded, true)[0];
        ValidateExecutable(first.Value);
        return new CommandSpec(first.Value, expanded[first.End..].TrimStart(' ', '\t'));
    }

    private static void ValidateExecutable(string executable)
    {
        if (string.IsNullOrWhiteSpace(executable) || executable.IndexOfAny(['\0', '"', '%', '\r', '\n']) >= 0)
            throw new ArgumentException("Некорректный исполняемый файл.");
        string name = Path.GetFileName(executable).ToLowerInvariant();
        if ((!name.EndsWith(".exe", StringComparison.Ordinal) && !name.EndsWith(".com", StringComparison.Ordinal)) ||
            name is "cmd.exe" or "powershell.exe" or "pwsh.exe" or "wscript.exe" or "cscript.exe" or "bash.exe" or "sh.exe" or "steam.exe" or "asa-ru-fix.exe")
            throw new ArgumentException("Shell, скрипты и рекурсивные wrappers не поддерживаются.");
    }

    private sealed record Token(string Value, int Start, int End);

    // Microsoft CRT rules: 2n slashes before a quote become n slashes; 2n+1 escape the quote.
    private static List<Token> Tokens(string command, bool strict)
    {
        ArgumentNullException.ThrowIfNull(command);
        var tokens = new List<Token>();
        int index = 0;
        while (index < command.Length)
        {
            while (index < command.Length && command[index] is ' ' or '\t') index++;
            if (index == command.Length) break;
            int start = index;
            bool inQuotes = false;
            var value = new StringBuilder();
            while (index < command.Length && (inQuotes || command[index] is not ' ' and not '\t'))
            {
                int slashes = 0;
                while (index < command.Length && command[index] == '\\') { slashes++; index++; }
                if (index < command.Length && command[index] == '"')
                {
                    value.Append('\\', slashes / 2);
                    if (slashes % 2 != 0) { value.Append('"'); index++; }
                    else if (inQuotes && index + 1 < command.Length && command[index + 1] == '"') { value.Append('"'); index += 2; }
                    else { inQuotes = !inQuotes; index++; }
                }
                else
                {
                    value.Append('\\', slashes);
                    if (index < command.Length && (inQuotes || command[index] is not ' ' and not '\t')) value.Append(command[index++]);
                }
            }
            if (strict && inQuotes) throw new ArgumentException("Незакрытые кавычки параметров запуска.", nameof(command));
            tokens.Add(new Token(value.ToString(), start, index));
        }
        return tokens;
    }
}
