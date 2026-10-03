using AsaRuFix.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace AsaRuFix.Tests;

[TestClass]
public sealed class CommandTests
{
    [TestMethod]
    public void QuotingRoundTripsWindowsArguments()
    {
        string[] args = [@"C:\Game Files\Ark.exe", "", "русский", "say \"hello\"", "trailing slash \\", @"plain\path", "-flag", "\t"];
        CollectionAssert.AreEqual(args, GameCommandBuilder.Parse(string.Join(" ", args.Select(GameCommandBuilder.Quote))));
    }

    [TestMethod]
    public void ReadsDocumentedWindowsCommandLineExamples()
    {
        CollectionAssert.AreEqual(new[] { "a b c", "d", "e" }, GameCommandBuilder.Parse("\"a b c\" d e"));
        CollectionAssert.AreEqual(new[] { "ab\"c", "\\", "d" }, GameCommandBuilder.Parse("\"ab\\\"c\" \"\\\\\" d"));
        CollectionAssert.AreEqual(new[] { @"a\\\b", "de fg", "h" }, GameCommandBuilder.Parse("a\\\\\\b d\"e f\"g h"));
    }

    [TestMethod]
    public void FlagsAreAppendedAsExactOriginalString()
    {
        var result = GameCommandBuilder.Build([@"C:\Game Files\Ark.exe", "", "a\"b"], " -high   -foo \"quoted value\"  ");
        Assert.AreEqual(@"C:\Game Files\Ark.exe", result.FileName);
        Assert.IsTrue(result.Arguments.EndsWith("  -high   -foo \"quoted value\"  ", StringComparison.Ordinal));
        CollectionAssert.AreEqual(new[] { "", "a\"b", "-high", "-foo", "quoted value" }, GameCommandBuilder.Parse(result.Arguments));
    }

    [TestMethod]
    public void ExistingExecutableWrapperReceivesReconstructedGameCommand()
    {
        var result = GameCommandBuilder.Build([@"C:\Game Files\Ark.exe", "русский", ""], "\"C:\\Tools\\Existing Wrapper.exe\" --before %command% --after");
        Assert.AreEqual(@"C:\Tools\Existing Wrapper.exe", result.FileName);
        CollectionAssert.AreEqual(new[] { "--before", @"C:\Game Files\Ark.exe", "русский", "", "--after" }, GameCommandBuilder.Parse(result.Arguments));
    }

    [TestMethod]
    public void CommandFirstTemplateLaunchesGame()
    {
        var result = GameCommandBuilder.Build(["Ark.exe", "-steam"], "%command% -high");
        Assert.AreEqual("Ark.exe", result.FileName);
        CollectionAssert.AreEqual(new[] { "-steam", "-high" }, GameCommandBuilder.Parse(result.Arguments));
    }

    [TestMethod]
    [DataRow("cmd.exe /c %command%")]
    [DataRow("wrapper.cmd %command%")]
    [DataRow("powershell.exe %command%")]
    [DataRow("set VAR=1 && %command%")]
    [DataRow("%ENV% %command%")]
    [DataRow("wrapper.exe \"%command%\"")]
    [DataRow("wrapper.exe x%command%")]
    [DataRow("%command% %command%")]
    [DataRow("-arg \"unfinished")]
    [DataRow("-flag | other.exe")]
    [DataRow("VAR=1 %command%")]
    public void ComplexOriginalOptionsFailClosed(string options) => Assert.ThrowsExactly<ArgumentException>(() => GameCommandBuilder.ValidateOriginal(options));

    [TestMethod]
    public void MissingGameExecutableIsRejected() => Assert.ThrowsExactly<ArgumentException>(() => GameCommandBuilder.Build([], ""));
}
