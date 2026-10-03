namespace AsaRuFix.Core;

public enum UiAction { None, Install, LocateArk, RepairIntegration, RepairInstallation, CheckTranslation, CheckProgram, OpenLog, Uninstall }
public sealed record UiServiceAction(UiAction Action, string Text, bool Enabled);
public sealed record MainWindowSnapshot
{
    public bool SteamFound { get; init; }
    public bool ArkFound { get; init; }
    public int ProfileCount { get; init; }
    public string? ProfileName { get; init; }
    public bool ProfileSelected { get; init; }
    public bool ExecutablePresent { get; init; }
    public bool ConfigFilePresent { get; init; }
    public bool ConfigValid { get; init; }
    public bool StateValid { get; init; }
    public bool IntegrationValid { get; init; }
    public bool ManagedOptionsReferenced { get; init; }
    public bool RecoverySafe { get; init; }
    public bool OptionsReadable { get; init; } = true;
    public bool PakVerified { get; init; }
    public string? TranslationVersion { get; init; }
    public bool RunningInstalledCopy { get; init; }
    public bool LogExists { get; init; }
}
public sealed record MainWindowState
{
    public bool Healthy { get; init; }
    public bool PartialInstallation { get; init; }
    public bool ShowProfileSelector { get; init; }
    public bool ShowProgress { get; init; }
    public string SteamStatus { get; init; } = "";
    public string ArkStatus { get; init; } = "";
    public string ProfileStatus { get; init; } = "";
    public string IntegrationStatus { get; init; } = "";
    public string TranslationStatus { get; init; } = "";
    public string Explanation { get; init; } = "";
    public UiAction PrimaryAction { get; init; }
    public string PrimaryText { get; init; } = "";
    public bool PrimaryEnabled { get; init; }
    public IReadOnlyList<UiServiceAction> Services { get; init; } = [];
}
public static class MainWindowStateBuilder
{
    public static MainWindowState Build(MainWindowSnapshot s, bool busy = false, bool preview = false)
    {
        bool installed = s.ExecutablePresent && s.ConfigValid;
        bool partial = (s.ExecutablePresent || s.ConfigFilePresent || s.ManagedOptionsReferenced) && !installed;
        bool ready = s.SteamFound && s.ArkFound && s.ProfileSelected && s.OptionsReadable;
        bool healthy = ready && installed && s.IntegrationValid && s.StateValid && s.PakVerified;
        UiAction primary;
        string explanation;
        if (!s.SteamFound)
        {
            primary = UiAction.None;
            explanation = "Steam не найден. Установите Steam, войдите в свой аккаунт и откройте ASA RU Fix снова.";
        }
        else if (!s.ArkFound)
        {
            primary = UiAction.LocateArk;
            explanation = "ARK не найдена. Укажите папку установленной игры.";
        }
        else if (partial)
        {
            primary = UiAction.RepairInstallation;
            explanation = "⚠ Обнаружена неполная установка ASA RU Fix.";
        }
        else if (!installed)
        {
            primary = UiAction.Install;
            explanation = "ASA RU Fix ещё не установлен.\n\nПосле установки перевод и программа будут обновляться автоматически. ARK можно будет запускать обычной кнопкой «Играть» в Steam.";
        }
        else if (!s.IntegrationValid || !s.OptionsReadable)
        {
            primary = UiAction.RepairIntegration;
            explanation = "Восстановите интеграцию, чтобы перевод и программа обновлялись при обычном запуске ARK через Steam.";
        }
        else if (!healthy)
        {
            primary = UiAction.RepairInstallation;
            explanation = "⚠ Установка перевода требует восстановления.";
        }
        else
        {
            primary = UiAction.None;
            explanation = "Автообновление перевода и программы включено.\n\nВсё готово.\nПросто запускайте ARK обычной кнопкой «Играть» в Steam.";
        }
        if (s.SteamFound && !s.ProfileSelected)
            explanation += "\n\nВыберите профиль Steam перед установкой или восстановлением.";
        if (primary is UiAction.Install or UiAction.RepairIntegration or UiAction.RepairInstallation && s.ProfileSelected && !s.RecoverySafe)
            explanation += "\n\nНе удалось подтвердить исходные параметры запуска. Автоматическое восстановление заблокировано. Восстановите исходные параметры ARK из своей резервной копии в свойствах игры в Steam, затем откройте программу снова. Если копии нет, обратитесь за помощью; не удаляйте неизвестные параметры вручную.";
        bool canChange = !busy && !preview;
        return new()
        {
            Healthy = healthy, PartialInstallation = partial, ShowProfileSelector = s.ProfileCount > 1,
            ShowProgress = busy,
            SteamStatus = s.SteamFound ? "✓ Steam найден" : "✕ Steam не найден",
            ArkStatus = s.ArkFound ? "✓ ARK найдена" : "✕ ARK не найдена",
            ProfileStatus = s.ProfileCount > 1 ? "Профиль Steam:" : s.ProfileSelected ? "Профиль Steam: " + s.ProfileName : "Профиль Steam не определён",
            IntegrationStatus = s.IntegrationValid && installed ? "✓ Интеграция со Steam работает" :
                partial ? "⚠ Обнаружена неполная установка ASA RU Fix" : installed ? "⚠ Интеграция со Steam требует восстановления" : "Интеграция со Steam ещё не настроена",
            TranslationStatus = s.PakVerified && s.StateValid ? "✓ Перевод v" + s.TranslationVersion + " установлен" : "Перевод не установлен или требует восстановления",
            Explanation = explanation, PrimaryAction = primary,
            PrimaryText = primary switch { UiAction.Install => "Установить и настроить", UiAction.LocateArk => "Указать папку ARK",
                UiAction.RepairIntegration => "Восстановить интеграцию Steam", UiAction.RepairInstallation => "Восстановить установку", _ => "" },
            PrimaryEnabled = canChange && (primary == UiAction.LocateArk || primary != UiAction.None && ready && s.RecoverySafe),
            Services = [
                new(UiAction.CheckTranslation, "Проверить перевод сейчас", canChange && installed && s.ArkFound),
                new(UiAction.CheckProgram, "Проверить обновление программы сейчас", canChange && installed && s.RunningInstalledCopy && s.ArkFound),
                new(UiAction.RepairIntegration, "Восстановить интеграцию Steam", canChange && installed && ready && s.RecoverySafe),
                new(UiAction.LocateArk, "Указать папку ARK вручную", canChange && s.SteamFound),
                new(UiAction.OpenLog, "Открыть лог", !busy && s.LogExists),
                new(UiAction.Uninstall, "Удалить ASA RU Fix", canChange && installed && s.SteamFound && s.ArkFound && s.RecoverySafe)
            ]
        };
    }
}
