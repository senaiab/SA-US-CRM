using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;

namespace SaUsErpInstaller
{
    internal static class SetupBootstrapper
    {
        private static int Main(string[] args)
        {
            string tempRoot = Path.Combine(Path.GetTempPath(), "SA-US-ERP-Setup-" + Guid.NewGuid().ToString("N"));

            try
            {
                Directory.CreateDirectory(tempRoot);

                ExtractResource("install.cmd", Path.Combine(tempRoot, "install.cmd"));
                ExtractResource("install.ps1", Path.Combine(tempRoot, "install.ps1"));
                ExtractResource("payload.zip", Path.Combine(tempRoot, "payload.zip"));

                var startInfo = new ProcessStartInfo
                {
                    FileName = "cmd.exe",
                    Arguments = "/d /s /c \"\"" + Path.Combine(tempRoot, "install.cmd") + "\" " + JoinArguments(args) + "\"",
                    WorkingDirectory = tempRoot,
                    UseShellExecute = false
                };

                using (Process process = Process.Start(startInfo))
                {
                    process.WaitForExit();
                    return process.ExitCode;
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("SA-US ERP installer failed.");
                Console.Error.WriteLine(ex.Message);
                Console.Error.WriteLine("Press any key to close.");
                Console.ReadKey();
                return 1;
            }
            finally
            {
                try
                {
                    if (Directory.Exists(tempRoot))
                    {
                        Directory.Delete(tempRoot, true);
                    }
                }
                catch
                {
                    // Temp cleanup failure should not make a successful install fail.
                }
            }
        }

        private static void ExtractResource(string resourceName, string outputPath)
        {
            Assembly assembly = Assembly.GetExecutingAssembly();
            using (Stream input = assembly.GetManifestResourceStream(resourceName))
            {
                if (input == null)
                {
                    throw new InvalidOperationException("Missing installer resource: " + resourceName);
                }

                using (FileStream output = File.Create(outputPath))
                {
                    input.CopyTo(output);
                }
            }
        }

        private static string JoinArguments(string[] args)
        {
            if (args == null || args.Length == 0)
            {
                return string.Empty;
            }

            string[] escaped = new string[args.Length];
            for (int i = 0; i < args.Length; i++)
            {
                escaped[i] = "\"" + args[i].Replace("\"", "\\\"") + "\"";
            }

            return string.Join(" ", escaped);
        }
    }
}
