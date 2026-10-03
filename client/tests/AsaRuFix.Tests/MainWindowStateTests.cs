using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public class MainWindowStateTests
{
    private static MainWindowSnapshot Fresh => new() { SteamFound = true, ArkFound = true, ProfileCount = 1,
        ProfileName = "Игрок", ProfileSelected = true, RecoverySafe = true };
    internal static MainWindowSnapshot Healthy => Fresh with { ExecutablePresent = true, ConfigFilePresent = true,
        ConfigValid = true, StateValid = true, IntegrationValid = true, PakVerified = true,
        TranslationVersion = "1.0.0", RunningInstalledCopy = true, LogExists = true };

    [TestMethod] public void FreshInstallationOffersInstallAndConfigure()
    {
        var state = MainWindowStateBuilder.Build(Fresh);
        Assert.AreEqual(UiAction.Install, state.PrimaryAction);
        Assert.AreEqual("Установить и настроить", state.PrimaryText);
        Assert.IsTrue(state.PrimaryEnabled);
    }
    [TestMethod] public void HealthyInstallationNeedsNoPrimaryAction()
    {
        var state = MainWindowStateBuilder.Build(Healthy);
        Assert.IsTrue(state.Healthy);
        Assert.AreEqual(UiAction.None, state.PrimaryAction);
        StringAssert.Contains(state.Explanation, "Всё готово.");
        StringAssert.Contains(state.Explanation, "Автообновление перевода и программы включено.");
        Assert.AreEqual("✓ Перевод v1.0.0 установлен", state.TranslationStatus);
        Assert.IsFalse(state.Explanation.Contains("последняя версия"));
    }
    [TestMethod] public void SingleProfileUsesPlainName()
    {
        var state = MainWindowStateBuilder.Build(Healthy);
        Assert.IsFalse(state.ShowProfileSelector);
        Assert.AreEqual("Профиль Steam: Игрок", state.ProfileStatus);
    }
    [TestMethod] public void MultipleProfilesShowSelector() =>
        Assert.IsTrue(MainWindowStateBuilder.Build(Healthy with { ProfileCount = 2 }).ShowProfileSelector);
    [TestMethod] public void AmbiguousProfileBlocksInstallAndRepair()
    {
        var state = MainWindowStateBuilder.Build(Fresh with { ProfileCount = 2, ProfileSelected = false, ProfileName = null });
        Assert.IsFalse(state.PrimaryEnabled);
        StringAssert.Contains(state.Explanation, "Выберите профиль Steam");
    }
    [TestMethod] public void MissingArkOffersFolderSelection()
    {
        var state = MainWindowStateBuilder.Build(Healthy with { ArkFound = false });
        Assert.AreEqual(UiAction.LocateArk, state.PrimaryAction);
        Assert.AreEqual("Указать папку ARK", state.PrimaryText);
        Assert.IsFalse(state.Services.Single(x => x.Action == UiAction.CheckTranslation).Enabled);
    }
    [TestMethod] public void BrokenIntegrationOffersRepair()
    {
        var state = MainWindowStateBuilder.Build(Healthy with { IntegrationValid = false });
        Assert.IsFalse(state.Healthy);
        Assert.AreEqual(UiAction.RepairIntegration, state.PrimaryAction);
        Assert.AreEqual("Восстановить интеграцию Steam", state.PrimaryText);
        StringAssert.Contains(state.IntegrationStatus, "требует восстановления");
    }
    [TestMethod] public void OrphanedWrapperIsPartialAndUnsafeRecoveryIsBlocked()
    {
        var state = MainWindowStateBuilder.Build(Fresh with { ManagedOptionsReferenced = true, RecoverySafe = false });
        Assert.IsTrue(state.PartialInstallation);
        Assert.IsFalse(state.Healthy);
        Assert.AreEqual(UiAction.RepairInstallation, state.PrimaryAction);
        Assert.AreEqual("Восстановить установку", state.PrimaryText);
        Assert.IsFalse(state.PrimaryEnabled);
        StringAssert.Contains(state.Explanation, "исходные параметры");
    }
    [TestMethod] public void PartialInstallationWithConfirmedOriginalCanBeRepaired()
    {
        var state = MainWindowStateBuilder.Build(Healthy with { ExecutablePresent = false, ManagedOptionsReferenced = true });
        Assert.IsTrue(state.PartialInstallation);
        Assert.IsTrue(state.PrimaryEnabled);
    }
    [TestMethod] public void IdleHidesProgress() => Assert.IsFalse(MainWindowStateBuilder.Build(Healthy).ShowProgress);
    [TestMethod] public void BusyShowsProgressAndDisablesActions()
    {
        var state = MainWindowStateBuilder.Build(Fresh, busy: true);
        Assert.IsTrue(state.ShowProgress);
        Assert.IsFalse(state.PrimaryEnabled);
        Assert.IsTrue(state.Services.All(x => !x.Enabled));
    }
    [TestMethod] public void ServiceMenuUsesOptionalCheckWording()
    {
        var state = MainWindowStateBuilder.Build(Healthy);
        Assert.AreEqual("Проверить перевод сейчас", state.Services.Single(x => x.Action == UiAction.CheckTranslation).Text);
        Assert.AreEqual("Проверить обновление программы сейчас", state.Services.Single(x => x.Action == UiAction.CheckProgram).Text);
        Assert.IsTrue(state.Services.All(x => x.Text != "Обновить перевод" && x.Text != "Обновить updater"));
        Assert.IsTrue(state.Services.All(x => x.Enabled));
    }
    [TestMethod] public void FreshInstallationDisablesMeaninglessServices()
    {
        var state = MainWindowStateBuilder.Build(Fresh);
        Assert.IsFalse(state.Services.Single(x => x.Action == UiAction.Uninstall).Enabled);
        Assert.IsFalse(state.Services.Single(x => x.Action == UiAction.CheckTranslation).Enabled);
        Assert.IsFalse(state.Services.Single(x => x.Action == UiAction.RepairIntegration).Enabled);
    }
    [TestMethod] public void PreviewBlocksEverySystemChangingAction()
    {
        var state = MainWindowStateBuilder.Build(Healthy, preview: true);
        Assert.IsTrue(state.Services.Where(x => x.Action != UiAction.OpenLog).All(x => !x.Enabled));
        Assert.IsTrue(state.Services.Single(x => x.Action == UiAction.OpenLog).Enabled);
        Assert.IsFalse(MainWindowStateBuilder.Build(Fresh, preview: true).PrimaryEnabled);
    }
    [TestMethod] public void MissingStateOrPakIsNotHealthy()
    {
        foreach (var snapshot in new[] { Healthy with { StateValid = false }, Healthy with { PakVerified = false } })
        {
            var state = MainWindowStateBuilder.Build(snapshot);
            Assert.IsFalse(state.Healthy);
            Assert.AreEqual(UiAction.RepairInstallation, state.PrimaryAction);
        }
    }
    [TestMethod] public void UnreadableSteamSettingsBlockRecovery()
    {
        var state = MainWindowStateBuilder.Build(Healthy with { OptionsReadable = false, RecoverySafe = false });
        Assert.IsFalse(state.Healthy);
        Assert.IsFalse(state.PrimaryEnabled);
    }
    [TestMethod] public void BootstrapDoesNotOfferSelfUpdateThatRequiresInstalledCopy() =>
        Assert.IsFalse(MainWindowStateBuilder.Build(Healthy with { RunningInstalledCopy = false })
            .Services.Single(x => x.Action == UiAction.CheckProgram).Enabled);
}
