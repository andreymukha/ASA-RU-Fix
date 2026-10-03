using System.Diagnostics;
using AsaRuFix.Core;

namespace AsaRuFix.App;

internal sealed class MainForm : Form
{
    private readonly TableLayoutPanel layout = new() { Dock = DockStyle.Fill, AutoSize = true,
        AutoSizeMode = AutoSizeMode.GrowAndShrink, ColumnCount = 1, Padding = new Padding(20) };
    private readonly Label steamStatus = StatusLabel("steamStatus");
    private readonly Label arkStatus = StatusLabel("arkStatus");
    private readonly Label profileStatus = StatusLabel("profileStatus");
    private readonly Label integrationStatus = StatusLabel("integrationStatus");
    private readonly Label translationStatus = StatusLabel("translationStatus");
    private readonly Label explanation = StatusLabel("explanation");
    private readonly ComboBox profiles = new() { Name = "profiles", Dock = DockStyle.Fill,
        DropDownStyle = ComboBoxStyle.DropDownList, TabIndex = 0, AccessibleName = "Профиль Steam" };
    private readonly Button primary = new() { Name = "primary", AutoSize = true,
        Padding = new Padding(10, 5, 10, 5), TabIndex = 1 };
    private readonly Button additional = new() { Name = "additional", Text = "Дополнительно ▾", AutoSize = true,
        Padding = new Padding(6, 5, 6, 5), TabIndex = 2 };
    private readonly ContextMenuStrip services = new();
    private readonly ToolTip pathsHint = new();
    private readonly ProgressBar progress = new() { Name = "progress", Dock = DockStyle.Fill, Height = 12, Visible = false };
    private readonly ConfigStore store = new(AppRuntime.Paths);
    private readonly WindowsPlatform platform = new();
    private readonly LocalLogger logger = new(AppRuntime.Paths);
    private readonly bool preview;
    private SteamInstallation? steam;
    private MainWindowSnapshot snapshot = new();
    private MainWindowState view = new();
    private bool busy, discovering;

    public MainForm(bool uninstall, bool preview = false)
    {
        this.preview = preview;
        Text = "ASA RU Fix " + AppRuntime.Version + (preview ? " — предпросмотр" : "");
        AutoScaleDimensions = new SizeF(96, 96);
        AutoScaleMode = AutoScaleMode.Dpi;
        AutoSize = true;
        AutoSizeMode = AutoSizeMode.GrowAndShrink;
        ClientSize = new Size(560, 360);
        MinimumSize = new Size(560, 0);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        var title = StatusLabel("title");
        title.Text = "ASA RU Fix " + AppRuntime.Version;
        title.Font = new Font(Font, FontStyle.Bold);
        title.Margin = new Padding(0, 0, 0, 12);
        AddRow(title);
        AddRow(steamStatus); AddRow(arkStatus); AddRow(profileStatus); AddRow(profiles);
        AddRow(integrationStatus); AddRow(translationStatus);
        explanation.Margin = new Padding(0, 14, 0, 10);
        AddRow(explanation);
        if (preview)
        {
            var notice = StatusLabel("previewNotice");
            notice.Text = "Предпросмотр — только чтение. Установка и изменения отключены.";
            AddRow(notice);
        }
        var actions = new FlowLayoutPanel { Name = "actions", Dock = DockStyle.Fill, AutoSize = true,
            AutoSizeMode = AutoSizeMode.GrowAndShrink, WrapContents = true, Margin = Padding.Empty };
        primary.Margin = new Padding(0, 8, 8, 0);
        additional.Margin = new Padding(0, 8, 0, 0);
        actions.Controls.AddRange([primary, additional]);
        AddRow(actions); AddRow(progress);
        Controls.Add(layout);
        primary.Click += async (_, _) => await RunActionAsync(view.PrimaryAction);
        additional.Click += (_, _) => services.Show(additional, new Point(0, additional.Height));
        profiles.SelectedIndexChanged += (_, _) => { if (!discovering) ShowStatus(); };
        ClientSizeChanged += (_, _) => WrapLabels();
        Shown += async (_, _) =>
        {
            try { Discover(); if (uninstall && !preview) await RunActionAsync(UiAction.Uninstall, requestedUninstall: true); }
            catch (Exception ex) { ShowError(ex); }
        };
        FormClosing += (_, e) => { if (busy) e.Cancel = true; };
        FormClosed += (_, _) => { services.Dispose(); pathsHint.Dispose(); };
        WrapLabels();
    }

    private static Label StatusLabel(string name) => new() { Name = name, AutoSize = true,
        Dock = DockStyle.Fill, Margin = new Padding(0, 3, 0, 3), UseMnemonic = false };
    private void AddRow(Control control)
    {
        int row = layout.RowCount++;
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.Controls.Add(control, 0, row);
    }
    private void WrapLabels()
    {
        int width = Math.Max(100, ClientSize.Width - layout.Padding.Horizontal);
        foreach (var label in layout.Controls.OfType<Label>()) label.MaximumSize = new Size(width, 0);
    }
    private void Discover()
    {
        steam = SteamDiscovery.Find();
        discovering = true;
        try
        {
            profiles.Items.Clear();
            if (steam is not null)
            {
                foreach (var user in steam.Users) profiles.Items.Add(user);
                profiles.DisplayMember = nameof(SteamUser.DisplayName);
                profiles.SelectedItem = steam.Users.Count == 1 ? steam.Users[0] : SteamUserResolver.Resolve(steam);
            }
        }
        finally { discovering = false; }
        ShowStatus();
    }
    private void ShowStatus()
    {
        snapshot = MainWindowSnapshotReader.Read(AppRuntime.Paths, steam, profiles.SelectedItem as SteamUser, Environment.ProcessPath);
        ApplyState(MainWindowStateBuilder.Build(snapshot, busy, preview));
        pathsHint.SetToolTip(steamStatus, steam?.SteamPath ?? "");
        pathsHint.SetToolTip(arkStatus, steam?.GamePath ?? "");
    }
    internal void ApplyState(MainWindowState state)
    {
        view = state;
        SuspendLayout(); layout.SuspendLayout();
        steamStatus.Text = state.SteamStatus; arkStatus.Text = state.ArkStatus;
        profileStatus.Text = state.ProfileStatus; profiles.Visible = state.ShowProfileSelector; profiles.Enabled = !busy;
        integrationStatus.Text = state.IntegrationStatus; translationStatus.Text = state.TranslationStatus;
        explanation.Text = state.Explanation;
        primary.Text = state.PrimaryText; primary.Visible = state.PrimaryAction != UiAction.None; primary.Enabled = state.PrimaryEnabled;
        AcceptButton = primary.Visible && primary.Enabled ? primary : null;
        progress.Visible = state.ShowProgress;
        additional.Enabled = !busy;
        services.Items.Clear();
        foreach (var service in state.Services)
        {
            if (service.Action == UiAction.Uninstall) services.Items.Add(new ToolStripSeparator());
            var item = new ToolStripMenuItem(service.Text) { Enabled = service.Enabled };
            var action = service.Action;
            item.Click += async (_, _) => await RunActionAsync(action);
            services.Items.Add(item);
        }
        WrapLabels(); layout.ResumeLayout(true); ResumeLayout(true);
    }
    private async Task RunActionAsync(UiAction action, bool requestedUninstall = false)
    {
        if (busy || action == UiAction.None || preview && action != UiAction.OpenLog) return;
        bool enabled = requestedUninstall && action == UiAction.Uninstall ||
            (action == view.PrimaryAction ? view.PrimaryEnabled : view.Services.Any(x => x.Action == action && x.Enabled));
        if (!enabled) return;
        if (action == UiAction.OpenLog)
        {
            var log = Path.Combine(AppRuntime.Paths.Logs, "updater.log");
            try { if (File.Exists(log)) Process.Start(new ProcessStartInfo(log) { UseShellExecute = true }); }
            catch (Exception ex) { ShowError(ex); }
            return;
        }
        if (action == UiAction.LocateArk)
        {
            try { ChooseGameFolder(); }
            catch (Exception ex) { ShowError(ex); }
            finally { ShowStatus(); }
            return;
        }
        busy = true; progress.Style = ProgressBarStyle.Marquee;
        ApplyState(MainWindowStateBuilder.Build(snapshot, busy, preview));
        try
        {
            switch (action)
            {
                case UiAction.Install: case UiAction.RepairIntegration: case UiAction.RepairInstallation: await IntegrateAsync(); break;
                case UiAction.CheckTranslation: await UpdateAsync(); break;
                case UiAction.CheckProgram: await UpdateSelfAsync(); break;
                case UiAction.Uninstall: await UninstallAsync(); break;
            }
        }
        catch (Exception ex) { ShowError(ex); }
        finally
        {
            busy = false;
            if (!IsDisposed) { progress.Value = 0; ShowStatus(); }
        }
    }
    private void ChooseGameFolder()
    {
        if (steam is null) throw new InvalidOperationException("Steam не найден. Установите Steam и войдите в аккаунт.");
        using var dialog = new FolderBrowserDialog { Description = "Выберите папку ARK: Survival Ascended" };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        if (!SteamDiscovery.IsGameDirectory(dialog.SelectedPath)) throw new InvalidOperationException("В выбранной папке нет ARK: Survival Ascended.");
        steam = steam with { GamePath = dialog.SelectedPath };
    }
    private void ReportProgress(double value)
    {
        progress.Style = ProgressBarStyle.Continuous;
        progress.Value = (int)Math.Clamp(value * 100, 0, 100);
    }
    private void ShowError(Exception ex)
    {
        if (!preview) logger.Write("manual-failed", ex.GetType().Name);
        MessageBox.Show(this, ex.Message + (preview ? "" : "\n\nЛог: " + Path.Combine(AppRuntime.Paths.Logs, "updater.log")),
            "ASA RU Fix — ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
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
                var pak = await AppRuntime.UpdatePakAsync(path, ct, new Progress<double>(ReportProgress));
                return (pak.Version, pak.Sha256);
            });
            await installer.InstallAsync(detected, user, Environment.ProcessPath!, AppRuntime.Version, CancellationToken.None);
            logger.Write("installed", AppRuntime.Version);
            MessageBox.Show(this, "ASA RU Fix установлен.\n\nПеревод и программа будут обновляться автоматически.\n\nТеперь просто запускайте ARK обычной кнопкой «Играть» в Steam.", "ASA-RU-Fix", MessageBoxButtons.OK, MessageBoxIcon.Information);
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
        var pak = await AppRuntime.UpdatePakAsync(game, CancellationToken.None, new Progress<double>(ReportProgress));
        store.SaveState(new() { TranslationVersion = pak.Version, TranslationSha256 = pak.Sha256, CheckedAt = DateTimeOffset.UtcNow.ToString("O") });
        MessageBox.Show(this, "Перевод v" + pak.Version + " установлен.", "ASA-RU-Fix");
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
        if (pending is null) { MessageBox.Show(this, "Установлена актуальная версия ASA RU Fix.", "ASA-RU-Fix"); return; }
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
        using var confirmation = new UninstallConfirmationDialog();
        await UninstallConfirmationDialog.RunConfirmedAsync(confirmation.ShowDialog(this), async () =>
        {
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
        });
    }
}
