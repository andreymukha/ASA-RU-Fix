namespace AsaRuFix.App;

internal sealed class UninstallConfirmationDialog : Form
{
    public UninstallConfirmationDialog()
    {
        Text = "Удалить ASA RU Fix?";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        StartPosition = FormStartPosition.CenterParent;
        MaximizeBox = false; MinimizeBox = false; ShowInTaskbar = false;
        AutoScaleDimensions = new SizeF(96, 96); AutoScaleMode = AutoScaleMode.Dpi;
        AutoSize = true; AutoSizeMode = AutoSizeMode.GrowAndShrink;
        var layout = new TableLayoutPanel { AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink,
            Dock = DockStyle.Fill, ColumnCount = 1, Padding = new Padding(20) };
        var description = new Label { Name = "description", AutoSize = true, Margin = new Padding(0, 0, 0, 18),
            Text = "Будут:\n\n• восстановлены исходные параметры запуска Steam;\n• удалён файл перевода;\n• удалён updater и его локальные данные." };
        var buttons = new FlowLayoutPanel { AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink,
            Anchor = AnchorStyles.Right, WrapContents = false, Margin = Padding.Empty };
        var delete = new Button { Name = "delete", Text = "Удалить", AutoSize = true,
            Padding = new Padding(10, 5, 10, 5), DialogResult = DialogResult.Yes, TabIndex = 1 };
        var cancel = new Button { Name = "cancel", Text = "Отмена", AutoSize = true,
            Padding = new Padding(10, 5, 10, 5), DialogResult = DialogResult.Cancel, TabIndex = 0 };
        buttons.Controls.Add(delete); buttons.Controls.Add(cancel);
        layout.Controls.Add(description); layout.Controls.Add(buttons); Controls.Add(layout);
        AcceptButton = cancel; CancelButton = cancel; ActiveControl = cancel;
        Shown += (_, _) => cancel.Select();
        FormClosing += (_, _) => { if (DialogResult != DialogResult.Yes) DialogResult = DialogResult.Cancel; };
    }

    internal static Task RunConfirmedAsync(DialogResult result, Func<Task> uninstall) =>
        result == DialogResult.Yes ? uninstall() : Task.CompletedTask;
}
