using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using AsaRuFix.Core;

namespace AsaRuFix.App;

internal static class AppRuntime
{
    public static AppPaths Paths => AppPaths.Default;
    public static string Version => Assembly.GetExecutingAssembly().GetName().Version!.ToString(3);
    public static string MutexName => "Local\\ASA-RU-Fix-" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Paths.Root.ToUpperInvariant())))[..24];

    public static async Task<PakUpdateResult> UpdatePakAsync(string gamePath, CancellationToken cancellation, IProgress<double>? progress = null)
    {
        using var http = ChannelClient.CreateHttpClient();
        return await new PakUpdater(new(http, Version)).UpdateAsync(gamePath, Paths.Updates,
            () => new WindowsPlatform().IsGameRunning(gamePath), progress, cancellation);
    }

    // This mode does not construct a logger or create the installation directory.
    public static async Task DiagnoseAsync(string output)
    {
        var steam = SteamDiscovery.Find();
        var user = steam is null ? null : SteamUserResolver.Resolve(steam);
        var store = new ConfigStore(Paths);
        var config = store.Load();
        var pak = steam?.GamePath is null ? null : Path.Combine(steam.GamePath, "ShooterGame/Content/Paks/ASA_RU_Fix_P.pak");
        var pakExists = pak is not null && File.Exists(pak);
        string? hash = pakExists ? AtomicFile.Sha256(pak!) : null;
        ChannelManifest? stable = null;
        string? error = null;
        try
        {
            using var http = ChannelClient.CreateHttpClient();
            stable = await new ChannelClient(http, Version).GetStableAsync(CancellationToken.None);
        }
        catch (Exception ex) { error = ex.GetType().Name; }
        string? options = user is null ? null : LaunchOptionsManager.Read(user.LocalConfigPath);
        var result = new
        {
            updater_version = Version,
            steam_found = steam is not null,
            ark_found = steam?.GamePath is not null,
            steam_user_resolved = user is not null,
            steam_profile_count = steam?.Users.Count ?? 0,
            integration_detected = options?.Contains(Paths.Executable, StringComparison.OrdinalIgnoreCase) == true,
            managed_integration_exact = options == LaunchOptionsManager.Managed(Paths.Executable),
            installed_updater_detected = File.Exists(Paths.Executable),
            config_present = config is not null,
            pak_exists = pakExists,
            pak_sha256 = hash,
            stable_manifest_reachable = stable is not null,
            stable_version = stable?.Version,
            current_translation_version = stable is not null && stable.Artifact.Sha256 == hash ? stable.Version : null,
            network_error = error
        };
        // Only the explicitly requested diagnostic output is written; no Steam paths/identity are exported.
        await File.WriteAllTextAsync(Path.GetFullPath(output), JsonSerializer.Serialize(result, ConfigStore.JsonOptions) + "\n");
    }

    public static async Task<int> SteamLaunchAsync(string[] arguments)
    {
        var store = new ConfigStore(Paths);
        var config = store.Load();
        var logger = new LocalLogger(Paths);
        string original = config?.OriginalLaunchOptions ?? "";
        string gamePath = config?.GamePath ?? "";
        try
        {
            var steam = SteamDiscovery.Find();
            if (steam?.GamePath is not null) gamePath = steam.GamePath;
            var user = steam is null ? null : SteamUserResolver.Resolve(steam);
            var profile = config?.Integrations.FirstOrDefault(x => x.AccountId == user?.AccountId);
            if (profile is not null) original = profile.OriginalLaunchOptions ?? "";
        }
        catch (Exception ex) { logger.Write("discovery-failed", ex.GetType().Name); }
        try { GameCommandBuilder.ValidateOriginal(original); }
        catch (Exception ex) { logger.Write("invalid-saved-options", ex.GetType().Name); original = ""; }

        UserMutex? lease = null;
        PendingSelfUpdate? pending = null;
        try
        {
            try { lease = UserMutex.TryAcquire(MutexName, TimeSpan.FromSeconds(2)); }
            catch (Exception ex) { logger.Write("mutex-failed", ex.GetType().Name); }
            var result = await new LaunchCoordinator().RunAsync(arguments, original, async _ =>
            {
                if (lease is null || !SteamDiscovery.IsGameDirectory(gamePath)) return;
                using var cancellation = new CancellationTokenSource();
                using var progress = new LaunchProgress(cancellation);
                try
                {
                    var pak = await UpdatePakAsync(gamePath, cancellation.Token, progress);
                    store.SaveState(new() { TranslationVersion = pak.Version, TranslationSha256 = pak.Sha256,
                        CheckedAt = DateTimeOffset.UtcNow.ToString("O") });
                    logger.Write("translation-" + pak.Status, pak.Version);
                }
                catch (Exception ex) { logger.Write("translation-failed-open", ex.GetType().Name); throw; }
            }, CancellationToken.None, async () =>
            {
                if (lease is null || config is null) return;
                try
                {
                    using var http = ChannelClient.CreateHttpClient();
                    pending = await SelfUpdateHelper.StageAndSaveAsync(new(http, Version), Version, CancellationToken.None);
                }
                catch (Exception ex) { logger.Write("self-update-stage-failed", ex.GetType().Name); }
            });
            if (pending is not null)
            {
                try { SelfUpdateHelper.StartCompletion(pending, false); }
                catch (Exception ex) { logger.Write("self-update-start-failed", ex.GetType().Name); }
            }
            return result;
        }
        finally { lease?.Dispose(); }
    }
}

internal sealed class LaunchProgress : IProgress<double>, IDisposable
{
    private readonly CancellationTokenSource cancellation;
    private readonly object gate = new();
    private bool started, done;
    private double value;
    private Form? form;
    public LaunchProgress(CancellationTokenSource cancellation)
    {
        this.cancellation = cancellation;
        _ = ShowAfterDelayAsync();
    }
    public void Report(double progress) { lock (gate) { started = true; value = progress; } }
    private async Task ShowAfterDelayAsync()
    {
        await Task.Delay(800);
        while (true)
        {
            lock (gate) { if (done) return; if (started) break; }
            await Task.Delay(100);
        }
        lock (gate)
        {
            if (done || !started) return;
            var thread = new Thread(() =>
            {
                using var window = new Form { Text = "Обновление перевода ASA", Width = 420, Height = 175,
                    StartPosition = FormStartPosition.CenterScreen, FormBorderStyle = FormBorderStyle.FixedDialog,
                    MaximizeBox = false, MinimizeBox = false };
                var bar = new ProgressBar { Left = 20, Top = 35, Width = 365 };
                var label = new Label { Text = "Загружается готовый перевод…", Left = 20, Top = 10, Width = 365 };
                var skip = new Button { Text = "Запустить без обновления", Left = 145, Top = 75, Width = 240 };
                skip.Click += (_, _) => { cancellation.Cancel(); window.Close(); };
                window.Controls.AddRange([label, bar, skip]);
                using var timer = new System.Windows.Forms.Timer { Interval = 100 };
                timer.Tick += (_, _) => { lock (gate) { if (done) window.Close(); else bar.Value = (int)Math.Clamp(value * 100, 0, 100); } };
                window.Shown += (_, _) => timer.Start();
                window.FormClosing += (_, _) => { lock (gate) { if (!done) cancellation.Cancel(); } };
                lock (gate) { if (done) return; form = window; }
                Application.Run(window);
            }) { IsBackground = true };
            thread.SetApartmentState(ApartmentState.STA);
            thread.Start();
        }
    }
    public void Dispose() { lock (gate) { done = true; if (form?.IsHandleCreated == true) form.BeginInvoke(() => form.Close()); } }
}
