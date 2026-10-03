using System.Text.Json;
if (int.TryParse(Environment.GetEnvironmentVariable("ASA_RU_FIX_FIXTURE_DELAY_MS"), out var delay)) await Task.Delay(delay);
File.WriteAllText(args[0], JsonSerializer.Serialize(args.Skip(2).ToArray()));
return int.Parse(args[1]);
