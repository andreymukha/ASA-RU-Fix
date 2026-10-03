using System.Diagnostics;
using AsaRuFix.Core;

namespace AsaRuFix.App;

internal sealed class MainForm : Form
{
    private readonly Label status = new() { Left = 20, Top = 20, Width = 640, Height = 100 };
    private readonly ComboBox profiles = new() { Left = 20, Top = 125, Width = 640, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly FlowLayoutPanel buttons = new() { Left = 20, Top = 165, Width = 640, Height = 100 };
    private readonly ProgressBar progress = new() { Left = 20, Top = 265, Width = 640 };
    private readonly ConfigStore store = new(AppRuntime.Paths);
    private readonly WindowsPlatform platform = new();
    private readonly LocalLogger logger = new(AppRuntime.Paths);
    private SteamInstallation? steam;
    private bool busy;

    public MainForm(bool uninstall)
    {
        Text = "ASA-RU-Fix " + AppRuntime.Version;
        ClientSize = new Size(685, 315);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Controls.AddRange([status, profiles, buttons, progress]);
        AddButton("Установить", () => IntegrateAsync());
        AddButton("Восстановить интеграцию Steam", () => IntegrateAsync());
        AddButton("Обновить перевод", UpdateAsync);
        AddButton("Обновить updater", UpdateSelfAsync);
        AddButton("Удалить", UninstallAsync);
        AddButton("Открыть лог", () => { Directory.CreateDirectory(AppRuntime.Paths.Logs); Process.Start(new ProcessStartInfo(AppRuntime.Paths.Logs) { UseShellExecute = true }); return Task.CompletedTask; });
        AddButton("Выбрать папку ARK", () =>
        {
            if (steam is null) throw new InvalidOperationException("Steam не найден. Установите Steam и войдите в аккаунт.");
            using var dialog = new FolderBrowserDialog { Description = "Выберите папку ARK: Survival Ascended" };
            if (dialog.ShowDialog(this) == DialogResult.OK)
            {
                if (!SteamDiscovery.IsGameDirectory(dialog.SelectedPath)) throw new InvalidOperationException("В выбранной папке нет ShooterGame/Binaries/Win64 и Content/Paks.");
                steam = steam with { GamePath = dialog.SelectedPath };
                ShowStatus();
            }
            return Task.CompletedTask;
        });
        Shown += async (_, _) => { try { Discover(); if (uninstall) await RunActionAsync(UninstallAsync); } catch (Exception ex) { ShowError(ex); } };
        FormClosing += (_, e) => { if (busy) e.Cancel = true; };
    }

    private void AddButton(string title, Func<Task> action)
    {
        var button = new Button { Text = title, AutoSize = true, Height = 35 };
        button.Click += async (_, _) => await RunActionAsync(action);
        buttons.Controls.Add(button);
    }
    private void Discover()
    {
        steam = SteamDiscovery.Find();
        profiles.Items.Clear();
        if (steam is not null)
        {
            foreach (var user in steam.Users) profiles.Items.Add(user);
            profiles.DisplayMember = nameof(SteamUser.DisplayName);
            profiles.SelectedItem = SteamUserResolver.Resolve(steam);
        }
        ShowStatus();
    }
    private void ShowStatus() => status.Text =
        $"Steam: {(steam is null ? "не найден" : steam.SteamPath)}\nARK: {steam?.GamePath ?? "не найдена — выберите папку"}\n" +
        (File.Exists(AppRuntime.Paths.Executable) ? "Updater установлен. " : "Updater ещё не установлен. ") +
        "Выберите профиль Steam. Существующие параметры запуска будут сохранены.";

    private async Task RunActionAsync(Func<Task> action)
    {
        if (busy) return;
        busy = true; buttons.Enabled = false; profiles.Enabled = false;
        try { await action(); }
        catch (Exception ex) { ShowError(ex); }
        finally { busy = false; buttons.Enabled = true; profiles.Enabled = true; progress.Value = 0; }
    }
    private void ShowError(Exception ex)
    {
        logger.Write("manual-failed", ex.GetType().Name);
        MessageBox.Show(this, ex.Message + "\n\nЛог: " + Path.Combine(AppRuntime.Paths.Logs, "updater.log"), "ASA-RU-Fix — ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }

    private async Task WithSteamClosedAsync(string steamPath, string gamePath, Func<Task> operation)
    {
        if (platform.IsGameRunning(gamePath)) throw new InvalidOperationException("Закройте ARK и повторите установку/обновление.");
        bool restart = false;
        if (platform.IsSteamRunning(steamPath))
        {
            using var dialog = new Form { Text = "Перезапуск Steam", ClientSize = new(500, 160), StartPosition = FormStartPosition.CenterParent,
                FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false, MinimizeBox = false };
            var text = new Label { Left = 15, Top = 15, Width = 465, Height = 65,
                Text = "Для настройки запуска ARK необходимо перезапустить Steam. Steam будет штатно закрыт, затем снова открыт." };
            var accept = new Button { Text = "Перезапустить Steam автоматически", Left = 15, Top = 100, Width = 330, DialogResult = DialogResult.OK };
            var cancel = new Button { Text = "Отмена", Left = 360, Top = 100, Width = 120, DialogResult = DialogResult.Cancel };
            dialog.Controls.AddRange([text, accept, cancel]); dialog.CancelButton = cancel;
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            restart = true;
            if (!await WindowsPlatform.ShutdownSteamAsync(steamPath)) throw new InvalidOperationException("Steam не завершился. Закройте его вручную и повторите операцию.");
        }
        try { await operation(); }
        finally { if (restart) WindowsPlatform.RestartSteam(steamPath); }
    }

    private async Task IntegrateAsync()
    {
        var detected = steam ?? throw new InvalidOperationException("Steam не найден.");
        var user = profiles.SelectedItem as SteamUser ?? throw new InvalidOperationException("Выберите аккаунт Steam. При нескольких профилях выбор обязателен.");
        var game = detected.GamePath ?? throw new InvalidOperationException("Выберите папку ARK.");
        using var lease = UserMutex.TryAcquire(AppRuntime.MutexName, TimeSpan.FromSeconds(2))
            ?? throw new InvalidOperationException("Другая операция updater уже выполняется. Повторите позже.");
        await WithSteamClosedAsync(detected.SteamPath, game, async () =>
        {
            var installer = new Installer(store, platform, async (path, ct) =>
            {
                var pak = await AppRuntime.UpdatePakAsync(path, ct, new Progress<double>(p => progress.Value = (int)Math.Clamp(p * 100, 0, 100)));
                return (pak.Version, pak.Sha256);
            });
            await installer.InstallAsync(detected, user, Environment.ProcessPath!, AppRuntime.Version, CancellationToken.None);
            logger.Write("installed", AppRuntime.Version);
            MessageBox.Show(this, "Перевод установлен. Запускайте ARK обычной кнопкой «Играть» в Steam.", "ASA-RU-Fix", MessageBoxButtons.OK, MessageBoxIcon.Information);
            ShowStatus();
        });
    }
    private async Task UpdateAsync()
    {
        var config = store.Load() ?? throw new InvalidOperationException("Сначала установите updater.");
        using var lease = UserMutex.TryAcquire(AppRuntime.MutexName, TimeSpan.FromSeconds(2))
            ?? throw new InvalidOperationException("Другая операция updater уже выполняется.");
        var game = steam?.GamePath ?? config.GamePath;
        if (platform.IsGameRunning(game)) throw new InvalidOperationException("Закройте ARK и повторите обновление.");
        var pak = await AppRuntime.UpdatePakAsync(game, CancellationToken.None, new Progress<double>(p => progress.Value = (int)Math.Clamp(p * 100, 0, 100)));
        store.SaveState(new() { TranslationVersion = pak.Version, TranslationSha256 = pak.Sha256, CheckedAt = DateTimeOffset.UtcNow.ToString("O") });
        MessageBox.Show(this, "Перевод обновлён: " + pak.Version, "ASA-RU-Fix");
    }
    private async Task UpdateSelfAsync()
    {
        if (!string.Equals(Environment.ProcessPath, AppRuntime.Paths.Executable, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Для self-update откройте установленный updater через меню «Пуск».");
        var config = store.Load() ?? throw new InvalidOperationException("Сначала установите updater.");
        if (platform.IsGameRunning(config.GamePath)) throw new InvalidOperationException("Закройте ARK и повторите обновление updater.");
        using var lease = UserMutex.TryAcquire(AppRuntime.MutexName, TimeSpan.FromSeconds(2))
            ?? throw new InvalidOperationException("Другая операция updater уже выполняется.");
        using var http = ChannelClient.CreateHttpClient();
        var pending = await SelfUpdateHelper.StageAndSaveAsync(new(http, AppRuntime.Version), AppRuntime.Version, CancellationToken.None);
        if (pending is null) { MessageBox.Show(this, "Установлена актуальная версия updater.", "ASA-RU-Fix"); return; }
        SelfUpdateHelper.StartCompletion(pending, true);
        busy = false; Close();
    }
    private async Task UninstallAsync()
    {
        if (!string.Equals(Environment.ProcessPath, AppRuntime.Paths.Executable, StringComparison.OrdinalIgnoreCase) && File.Exists(AppRuntime.Paths.Executable))
        {
            Process.Start(new ProcessStartInfo(AppRuntime.Paths.Executable, "--uninstall") { UseShellExecute = false });
            busy = false; Close(); return;
        }
        var config = store.Load() ?? throw new InvalidOperationException("Нет сохранённой интеграции для удаления.");
        if (MessageBox.Show(this, "Удалить updater и его PAK, восстановив исходные параметры Steam?", "Удаление ASA-RU-Fix", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK) return;
        using var lease = UserMutex.TryAcquire(AppRuntime.MutexName, TimeSpan.FromSeconds(2))
            ?? throw new InvalidOperationException("Другая операция updater уже выполняется.");
        bool removed = false;
        await WithSteamClosedAsync(config.SteamPath, config.GamePath, () =>
        {
            // Create a verified helper BEFORE uninstalling, so a copy failure leaves the installation intact.
            var helper = UninstallHelper.Prepare();
            try
            {
                new Uninstaller(store, platform).RemoveIntegrationAndData();
                UninstallHelper.Start(helper);
            }
            catch { UninstallHelper.RemovePrepared(helper); throw; }
            removed = true;
            return Task.CompletedTask;
        });
        if (removed) { busy = false; Close(); }
    }
}
