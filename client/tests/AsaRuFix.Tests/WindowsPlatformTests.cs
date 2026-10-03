using AsaRuFix.App;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public sealed class WindowsPlatformTests
{
    [TestMethod]
    public void ProcessPathMustBelongToExactSteamInstallation()
    {
        Assert.IsTrue(WindowsPlatform.ProcessMatches("steam", @"C:\Steam\steam.exe", @"C:\Steam", false));
        Assert.IsFalse(WindowsPlatform.ProcessMatches("steam", @"C:\Steam2\steam.exe", @"C:\Steam", false));
        Assert.IsFalse(WindowsPlatform.ProcessMatches("steamservice", @"C:\Steam\steamservice.exe", @"C:\Steam", false));
        Assert.IsTrue(WindowsPlatform.ProcessMatches("steamwebhelper", @"C:\Steam\bin\cef\steamwebhelper.exe", @"C:\Steam", false));
    }

    [TestMethod]
    public void InaccessibleKnownProcessIsTreatedAsRunning()
    {
        Assert.IsTrue(WindowsPlatform.ProcessMatches("steam", null, @"C:\Steam", false));
        Assert.IsTrue(WindowsPlatform.ProcessMatches("ArkAscended", null, @"D:\ARK", true));
        Assert.IsFalse(WindowsPlatform.ProcessMatches("unrelated", null, @"D:\ARK", true));
    }

    [TestMethod]
    public void GameBinaryMustBelongToSelectedGameRoot()
    {
        Assert.IsTrue(WindowsPlatform.ProcessMatches("ArkAscended", @"D:\ARK\ShooterGame\Binaries\Win64\ArkAscended.exe", @"D:\ARK", true));
        Assert.IsFalse(WindowsPlatform.ProcessMatches("ArkAscended", @"D:\ARK2\ShooterGame\Binaries\Win64\ArkAscended.exe", @"D:\ARK", true));
        Assert.IsTrue(WindowsPlatform.ProcessMatches("steam", @"D:\ARK\steam.exe", @"D:\ARK", true));
    }

    [TestMethod]
    public void AnyExecutableInsideArkInstallationBlocksPakChanges()
    {
        Assert.IsTrue(WindowsPlatform.ProcessMatches("NewArkExe", @"D:\ARK\SomeFolder\NewArkExe.exe", @"D:\ARK", true));
        Assert.IsFalse(WindowsPlatform.ProcessMatches("NewArkExe", @"D:\ARK2\NewArkExe.exe", @"D:\ARK", true));
        Assert.IsFalse(WindowsPlatform.ProcessMatches("NewArkExe", null, @"D:\ARK", true));
    }

    [TestMethod]
    public void RegistrationRequiresOwnerMarkerAndExpectedInstallation()
    {
        const string exe = @"C:\Users\Player\AppData\Local\ASA-RU-Fix\ASA-RU-Fix.exe";
        Assert.IsTrue(WindowsPlatform.OwnedRegistration(WindowsPlatform.OwnerMarker, Path.GetDirectoryName(exe), exe));
        Assert.IsFalse(WindowsPlatform.OwnedRegistration("foreign", Path.GetDirectoryName(exe), exe));
        Assert.IsFalse(WindowsPlatform.OwnedRegistration(WindowsPlatform.OwnerMarker, @"C:\Other", exe));
        Assert.IsFalse(WindowsPlatform.OwnedRegistration(null, Path.GetDirectoryName(exe), exe));
    }
}
