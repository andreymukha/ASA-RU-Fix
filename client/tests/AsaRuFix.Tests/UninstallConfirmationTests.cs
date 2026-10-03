using System.Runtime.ExceptionServices;
using AsaRuFix.App;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public class UninstallConfirmationTests
{
    [TestMethod]
    [DataRow(DialogResult.Cancel, false)]
    [DataRow(DialogResult.None, false)]
    [DataRow(DialogResult.OK, false)]
    [DataRow(DialogResult.Yes, true)]
    public async Task OnlyExplicitDeleteStartsUninstall(DialogResult result, bool expected)
    {
        bool called = false;
        await UninstallConfirmationDialog.RunConfirmedAsync(result, () => { called = true; return Task.CompletedTask; });
        Assert.AreEqual(expected, called);
    }

    [TestMethod]
    [DataRow("Enter", DialogResult.Cancel)]
    [DataRow("Escape", DialogResult.Cancel)]
    [DataRow("Close", DialogResult.Cancel)]
    [DataRow("Delete", DialogResult.Yes)]
    public void UserActionReturnsExpectedConfirmation(string action, DialogResult expected)
    {
        Exception? failure = null;
        var thread = new Thread(() =>
        {
            try
            {
                using var dialog = new UninstallConfirmationDialog { ShowInTaskbar = false,
                    StartPosition = FormStartPosition.Manual, Location = new Point(-32000, -32000) };
                dialog.Shown += (_, _) => dialog.BeginInvoke((Action)(() =>
                {
                    if (action == "Close") dialog.Close();
                    else if (action == "Delete") ((Button)dialog.Controls.Find("delete", true).Single()).PerformClick();
                    else typeof(Form).GetMethod("ProcessDialogKey", System.Reflection.BindingFlags.Instance |
                        System.Reflection.BindingFlags.NonPublic)!.Invoke(dialog,
                            [action == "Enter" ? Keys.Enter : Keys.Escape]);
                }));
                var result = dialog.ShowDialog();
                Assert.AreEqual(expected, result);
                bool called = false;
                UninstallConfirmationDialog.RunConfirmedAsync(result,
                    () => { called = true; return Task.CompletedTask; }).GetAwaiter().GetResult();
                Assert.AreEqual(action == "Delete", called);
            }
            catch (Exception error) { failure = error; }
        });
        thread.SetApartmentState(ApartmentState.STA); thread.Start(); thread.Join();
        if (failure is not null) ExceptionDispatchInfo.Capture(failure).Throw();
    }
    [TestMethod]
    [DataRow(100)]
    [DataRow(125)]
    [DataRow(150)]
    public void DialogHasSafeDefaultsAndFitsAtDpi(int percent)
    {
        Exception? failure = null;
        var thread = new Thread(() =>
        {
            try
            {
                using var dialog = new UninstallConfirmationDialog();
                Assert.AreEqual("Удалить ASA RU Fix?", dialog.Text);
                Assert.AreEqual(FormBorderStyle.FixedDialog, dialog.FormBorderStyle);
                Assert.AreEqual(FormStartPosition.CenterParent, dialog.StartPosition);
                Assert.IsFalse(dialog.MaximizeBox); Assert.IsFalse(dialog.MinimizeBox);
                Assert.AreEqual("Отмена", ((Button)dialog.AcceptButton!).Text);
                Assert.AreSame(dialog.AcceptButton, dialog.CancelButton);
                Assert.AreEqual(DialogResult.Cancel, dialog.CancelButton!.DialogResult);
                dialog.ShowInTaskbar = false; dialog.StartPosition = FormStartPosition.Manual;
                dialog.Location = new Point(-32000, -32000); dialog.Show();
                dialog.Scale(new SizeF(percent / 100f, percent / 100f)); dialog.PerformLayout();
                foreach (var label in dialog.Controls.Find("description", true).Cast<Label>())
                    Assert.IsTrue(label.GetPreferredSize(new Size(label.Width, 0)).Height <= label.Height);
                var delete = (Button)dialog.Controls.Find("delete", true).Single();
                Assert.AreEqual("Удалить", delete.Text);
                Assert.AreEqual(DialogResult.Yes, delete.DialogResult);
                Assert.AreNotSame(delete, dialog.AcceptButton);
                dialog.Close(); Assert.AreEqual(DialogResult.Cancel, dialog.DialogResult);
            }
            catch (Exception error) { failure = error; }
        });
        thread.SetApartmentState(ApartmentState.STA); thread.Start(); thread.Join();
        if (failure is not null) ExceptionDispatchInfo.Capture(failure).Throw();
    }
}
