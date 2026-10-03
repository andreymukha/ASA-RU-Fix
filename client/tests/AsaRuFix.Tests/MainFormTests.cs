using System.Reflection;
using System.Runtime.ExceptionServices;
using AsaRuFix.App;
using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public class MainFormTests
{
    private static void OnSta(Action action)
    {
        Exception? failure = null;
        var thread = new Thread(() => { try { action(); } catch (Exception error) { failure = error; } });
        thread.SetApartmentState(ApartmentState.STA); thread.Start(); thread.Join();
        if (failure is not null) ExceptionDispatchInfo.Capture(failure).Throw();
    }
    private static IEnumerable<Control> AllControls(Control parent) => parent.Controls.Cast<Control>()
        .SelectMany(child => new[] { child }.Concat(AllControls(child)));
    private static MainForm OpenPreview()
    {
        var form = new MainForm(uninstall: false, preview: true) { ShowInTaskbar = false,
            StartPosition = FormStartPosition.Manual, Location = new Point(-32000, -32000) };
        form.Show(); return form;
    }
    [TestMethod]
    [DataRow(100)] [DataRow(125)] [DataRow(150)]
    public void RussianLayoutFitsAtPreviewScale(int percent) => OnSta(() =>
    {
        using var form = OpenPreview();
        if (percent != 100) form.Scale(new SizeF(percent / 100f, percent / 100f));
        foreach (var snapshot in new[] { MainWindowStateTests.Healthy, MainWindowStateTests.Healthy with { IntegrationValid = false },
            MainWindowStateTests.Healthy with { ExecutablePresent = false, RecoverySafe = false, ProfileCount = 2 } })
        {
            form.ApplyState(MainWindowStateBuilder.Build(snapshot, preview: true)); form.PerformLayout();
            foreach (var control in AllControls(form).Where(x => x.Visible))
            {
                Assert.IsTrue(control.Right <= control.Parent!.ClientSize.Width, control.Name + " выходит за ширину");
                Assert.IsTrue(control.Bottom <= control.Parent!.ClientSize.Height, control.Name + " выходит за высоту");
                if (control is Label label)
                    Assert.IsTrue(label.GetPreferredSize(new Size(label.Width, 0)).Height <= label.Height, label.Name + " обрезан");
                if (control is Button button)
                    Assert.IsTrue(button.GetPreferredSize(Size.Empty).Width <= button.Width, button.Name + " обрезан");
            }
        }
    });
    [TestMethod] public void HealthyViewHidesPrimaryAndProgress() => OnSta(() =>
    {
        using var form = OpenPreview(); form.ApplyState(MainWindowStateBuilder.Build(MainWindowStateTests.Healthy, preview: true));
        Assert.IsFalse(AllControls(form).Single(x => x.Name == "primary").Visible);
        Assert.IsFalse(AllControls(form).Single(x => x.Name == "profiles").Visible);
        Assert.IsFalse(AllControls(form).Single(x => x.Name == "progress").Visible);
        Assert.IsNull(form.AcceptButton); Assert.IsNull(form.CancelButton);
    });
    [TestMethod] public void RequiredPrimaryIsDefaultAndDeleteNeverIs() => OnSta(() =>
    {
        using var form = OpenPreview();
        form.ApplyState(MainWindowStateBuilder.Build(MainWindowStateTests.Healthy with { IntegrationValid = false }));
        Assert.AreEqual("Восстановить интеграцию Steam", ((Button)form.AcceptButton!).Text);
        Assert.IsNull(form.CancelButton);
    });
    [TestMethod] public void PreviewGuardBlocksWritesEvenIfCallerEnablesAnAction() => OnSta(() =>
    {
        using var form = OpenPreview();
        form.ApplyState(MainWindowStateBuilder.Build(MainWindowStateTests.Healthy with { IntegrationValid = false }));
        var run = typeof(MainForm).GetMethod("RunActionAsync", BindingFlags.NonPublic | BindingFlags.Instance)!;
        foreach (var action in Enum.GetValues<UiAction>().Where(x => x != UiAction.OpenLog))
        {
            var task = (Task)run.Invoke(form, [action, true])!;
            Assert.IsTrue(task.IsCompletedSuccessfully);
        }
    });
}
