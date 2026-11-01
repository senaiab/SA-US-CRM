using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

namespace SaUsErpInstaller
{
    static class Program
    {
        [STAThread]
        static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            using (var form = new WizardForm())
            {
                Application.Run(form);
                return form.ExitCode;
            }
        }
    }

    class WizardForm : Form
    {
        private Panel[] _pages;
        private Panel _content;
        private int _currentPage;

        private Button _btnBack, _btnNext, _btnCancel;

        // Page 1 — Mode
        private RadioButton _rbServer, _rbClient, _rbBoth;

        // Page 2 — Directory
        private TextBox _txtDir;

        // Page 3 — Progress
        private ProgressBar _progressBar;
        private RichTextBox _rtbLog;

        // Page 4 — Done
        private Label _lblDoneTitle, _lblDoneDetail;
        private Button _btnOpenFolder, _btnViewLog;

        private bool _installSuccess;
        private string _installDir;
        private string _existingDir;

        public int ExitCode { get; private set; }

        public WizardForm()
        {
            _existingDir = GetExistingInstallDir();

            Text            = "SA-US ERP Setup";
            Size            = new Size(590, 510);
            StartPosition   = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox     = false;
            MinimizeBox     = false;
            Font            = new Font("Segoe UI", 9.5f);

            BuildLayout();
            GoToPage(0);
        }

        // ── Layout ────────────────────────────────────────────────────────────

        private void BuildLayout()
        {
            // Header band
            var header = new Panel { Dock = DockStyle.Top, Height = 70, BackColor = Color.FromArgb(24, 103, 192) };
            header.Paint += (s, e) =>
            {
                e.Graphics.DrawString("SA-US ERP Setup",
                    new Font("Segoe UI", 15, FontStyle.Bold), Brushes.White, 20f, 8f);
                e.Graphics.DrawString("SA Ultimate Solutions — Enterprise Resource Planning",
                    new Font("Segoe UI", 9), new SolidBrush(Color.FromArgb(190, 225, 255)), 22f, 44f);
            };
            Controls.Add(header);

            // Content area — must be added BEFORE bottom bar so Fill gets remaining space
            // Pages are swapped in/out one at a time to avoid multi-Fill clipping bugs
            _content = new Panel { Dock = DockStyle.Fill };
            _pages = new Panel[5];
            _pages[0] = BuildPage0_Welcome();
            _pages[1] = BuildPage1_Mode();
            _pages[2] = BuildPage2_Directory();
            _pages[3] = BuildPage3_Progress();
            _pages[4] = BuildPage4_Done();
            foreach (var p in _pages) p.Dock = DockStyle.Fill;
            Controls.Add(_content);

            // Button bar — added after Fill so it docks to bottom correctly
            var bar = new Panel { Dock = DockStyle.Bottom, Height = 52, BackColor = Color.FromArgb(242, 242, 242) };
            bar.Paint += (s, e) => e.Graphics.DrawLine(new Pen(Color.FromArgb(200, 200, 200)), 0, 0, bar.Width, 0);

            _btnCancel = NavBtn("Cancel",  ClientSize.Width - 108);
            _btnNext   = NavBtn("Next >",  ClientSize.Width - 210);
            _btnBack   = NavBtn("< Back",  ClientSize.Width - 312);

            _btnNext.Click   += OnNext;
            _btnBack.Click   += (s, e) => GoToPage(_currentPage - 1);
            _btnCancel.Click += OnCancel;

            bar.Controls.AddRange(new Control[] { _btnBack, _btnNext, _btnCancel });
            Controls.Add(bar);
        }

        private Button NavBtn(string text, int x)
        {
            return new Button
            {
                Text = text, Size = new Size(96, 32),
                Location = new Point(x, 10),
                Anchor = AnchorStyles.Right | AnchorStyles.Bottom
            };
        }

        // ── Page builders ─────────────────────────────────────────────────────

        private Panel BuildPage0_Welcome()
        {
            var p = new Panel();
            p.Controls.Add(Title("Welcome to SA-US ERP Setup", 24, 22));
            p.Controls.Add(BodyLabel(
                "This wizard will install SA-US ERP v2.5.0 on your computer.\n\n" +
                "SA-US ERP is a business management system that includes:\n\n" +
                "   Server — runs on the main office PC (MariaDB database included)\n" +
                "   Client — runs on any staff PC and connects to the server\n\n" +
                "Click Next to continue or Cancel to exit.",
                24, 76, 530));
            return p;
        }

        private Panel BuildPage1_Mode()
        {
            var p = new Panel();

            if (_existingDir != null)
            {
                p.Controls.Add(Title("Existing Installation Found", 24, 22));
                p.Controls.Add(BodyLabel(
                    "SA-US ERP is already installed at:\n" + _existingDir +
                    "\n\nChoose a component set to repair / reinstall:", 24, 68, 530));
            }
            else
            {
                p.Controls.Add(Title("Choose Installation Type", 24, 22));
                p.Controls.Add(BodyLabel("Choose what to install on this machine:", 24, 68, 530));
            }

            _rbServer = Radio("Server only  —  main office PC",                         40, 116);
            _rbClient = Radio("Client only  —  staff PC connecting over the network",    40, 148);
            _rbBoth   = Radio("Both server and client  (recommended, single-PC setup)",  40, 180);
            _rbBoth.Checked = true;

            p.Controls.AddRange(new Control[] { _rbServer, _rbClient, _rbBoth });
            return p;
        }

        private Panel BuildPage2_Directory()
        {
            var p = new Panel();
            p.Controls.Add(Title("Choose Install Location", 24, 22));
            p.Controls.Add(BodyLabel(
                "SA-US ERP will be installed to the folder shown below.\n" +
                "Click Browse to choose a different location.", 24, 68, 530));

            p.Controls.Add(SmallLabel("Destination folder:", 24, 136));

            var defaultPath = _existingDir ??
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                             "Programs", "SA-US ERP");

            _txtDir = new TextBox { Text = defaultPath, Font = new Font("Segoe UI", 10), Size = new Size(412, 26), Location = new Point(24, 158) };

            var btnBrowse = new Button { Text = "Browse...", Size = new Size(90, 26), Location = new Point(442, 158) };
            btnBrowse.Click += (s, e) =>
            {
                using (var dlg = new FolderBrowserDialog { Description = "Choose install folder", SelectedPath = _txtDir.Text })
                    if (dlg.ShowDialog() == DialogResult.OK) _txtDir.Text = dlg.SelectedPath;
            };

            p.Controls.AddRange(new Control[] { _txtDir, btnBrowse });
            return p;
        }

        private Panel BuildPage3_Progress()
        {
            var p = new Panel();
            p.Controls.Add(Title("Installing SA-US ERP...", 24, 22));

            _progressBar = new ProgressBar
            {
                Style = ProgressBarStyle.Marquee, MarqueeAnimationSpeed = 25,
                Size = new Size(538, 22), Location = new Point(24, 62)
            };

            _rtbLog = new RichTextBox
            {
                ReadOnly = true,
                BackColor = Color.FromArgb(28, 28, 28),
                ForeColor = Color.FromArgb(212, 212, 212),
                Font = new Font("Consolas", 8.5f),
                Size = new Size(538, 218),
                Location = new Point(24, 95),
                ScrollBars = RichTextBoxScrollBars.Vertical,
                WordWrap = true
            };

            p.Controls.AddRange(new Control[] { _progressBar, _rtbLog });
            return p;
        }

        private Panel BuildPage4_Done()
        {
            var p = new Panel();

            _lblDoneTitle = new Label
            {
                Font = new Font("Segoe UI", 14, FontStyle.Bold),
                AutoSize = true, Location = new Point(24, 26)
            };

            _lblDoneDetail = new Label
            {
                Font = new Font("Segoe UI", 10),
                AutoSize = false, Size = new Size(530, 110),
                Location = new Point(24, 78)
            };

            _btnOpenFolder = new Button
            {
                Text = "Open Install Folder", Size = new Size(168, 34),
                Location = new Point(24, 198)
            };
            _btnOpenFolder.Click += (s, e) =>
            {
                if (!string.IsNullOrEmpty(_installDir) && Directory.Exists(_installDir))
                    Process.Start("explorer.exe", _installDir);
            };

            _btnViewLog = new Button
            {
                Text = "View Installation Log", Size = new Size(168, 34),
                Location = new Point(200, 198), Visible = false
            };
            _btnViewLog.Click += (s, e) =>
            {
                var logForm = new Form
                {
                    Text = "Installation Log — SA-US ERP",
                    Size = new Size(620, 460),
                    StartPosition = FormStartPosition.CenterParent,
                    Font = new Font("Segoe UI", 9.5f),
                    MinimizeBox = false
                };
                var rtb = new RichTextBox
                {
                    Dock = DockStyle.Fill,
                    ReadOnly = true,
                    BackColor = Color.FromArgb(28, 28, 28),
                    ForeColor = Color.FromArgb(212, 212, 212),
                    Font = new Font("Consolas", 8.5f),
                    Text = _rtbLog.Text,
                    ScrollBars = RichTextBoxScrollBars.Vertical
                };
                logForm.Controls.Add(rtb);
                logForm.ShowDialog(this);
            };

            p.Controls.AddRange(new Control[] { _lblDoneTitle, _lblDoneDetail, _btnOpenFolder, _btnViewLog });
            return p;
        }

        // ── Navigation ────────────────────────────────────────────────────────

        private void GoToPage(int page)
        {
            _currentPage = page;
            _content.Controls.Clear();
            _content.Controls.Add(_pages[page]);

            _btnBack.Enabled   = page > 0 && page < 3;
            _btnCancel.Visible = page < 4;
            _btnNext.Enabled   = true;
            _btnNext.Visible   = true;

            switch (page)
            {
                case 0:
                case 1:
                    _btnNext.Text = "Next >";
                    break;
                case 2:
                    _btnNext.Text = "Install";
                    break;
                case 3:
                    _btnBack.Enabled   = false;
                    _btnNext.Enabled   = false;
                    _btnCancel.Enabled = false;
                    StartInstall();
                    break;
                case 4:
                    _btnBack.Enabled = false;
                    _btnNext.Text    = "Finish";
                    break;
            }
        }

        private void OnNext(object s, EventArgs e)
        {
            if (_currentPage == 4) { ExitCode = _installSuccess ? 0 : 1; Close(); return; }

            if (_currentPage == 2 && string.IsNullOrWhiteSpace(_txtDir.Text))
            {
                MessageBox.Show("Please choose an installation folder.", "Required",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            GoToPage(_currentPage + 1);
        }

        private void OnCancel(object s, EventArgs e)
        {
            if (MessageBox.Show("Are you sure you want to cancel?", "SA-US ERP Setup",
                    MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
            { ExitCode = 1; Close(); }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (_currentPage == 3) { e.Cancel = true; return; }
            base.OnFormClosing(e);
        }

        // ── Install ───────────────────────────────────────────────────────────

        private void StartInstall()
        {
            _installDir = _txtDir.Text.Trim();
            new Thread(RunInstall) { IsBackground = true }.Start();
        }

        private void RunInstall()
        {
            string tempRoot = Path.Combine(Path.GetTempPath(),
                "SA-US-ERP-" + Guid.NewGuid().ToString("N").Substring(0, 10));
            try
            {
                Log("SA-US ERP Installer v2.5.0", Color.FromArgb(110, 185, 255));
                Log(new string('-', 42), Color.FromArgb(70, 70, 70));
                Log("Extracting installer resources...");

                Directory.CreateDirectory(tempRoot);
                ExtractRes("install.cmd", Path.Combine(tempRoot, "install.cmd"));
                ExtractRes("install.ps1", Path.Combine(tempRoot, "install.ps1"));
                ExtractRes("payload.zip", Path.Combine(tempRoot, "payload.zip"));

                Log("Resources extracted.", Color.FromArgb(100, 210, 100));

                string mode = "both";
                Invoke(new Action(() =>
                {
                    if (_rbServer.Checked)      mode = "server";
                    else if (_rbClient.Checked) mode = "client";
                    else                        mode = "both";
                }));

                Log("Mode      : " + mode);
                Log("Directory : " + _installDir);
                Log("");
                Log("Starting install script...", Color.FromArgb(110, 185, 255));

                var psi = new ProcessStartInfo
                {
                    FileName  = "powershell.exe",
                    Arguments = string.Format(
                        "-NoProfile -ExecutionPolicy Bypass -File \"{0}\"" +
                        " -InstallMode \"{1}\" -InstallDir \"{2}\" -SkipMaintenanceDialog",
                        Path.Combine(tempRoot, "install.ps1"), mode, _installDir),
                    WorkingDirectory       = tempRoot,
                    UseShellExecute        = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError  = true,
                    CreateNoWindow         = true
                };

                int exitCode;
                using (var proc = Process.Start(psi))
                {
                    proc.OutputDataReceived += (s, e2) => { if (e2.Data != null) Log(e2.Data); };
                    proc.ErrorDataReceived  += (s, e2) => { if (e2.Data != null) Log("[!] " + e2.Data, Color.FromArgb(255, 165, 80)); };
                    proc.BeginOutputReadLine();
                    proc.BeginErrorReadLine();
                    proc.WaitForExit();
                    exitCode = proc.ExitCode;
                }

                _installSuccess = exitCode == 0;
                Log("");
                Log(_installSuccess
                    ? "Installation completed successfully."
                    : "Installation failed (exit code " + exitCode + ").",
                    _installSuccess ? Color.FromArgb(100, 210, 100) : Color.FromArgb(255, 100, 100));
            }
            catch (Exception ex)
            {
                Log("");
                Log("FATAL: " + ex.Message, Color.FromArgb(255, 100, 100));
                _installSuccess = false;
            }
            finally
            {
                try { if (Directory.Exists(tempRoot)) Directory.Delete(tempRoot, true); } catch { }
            }

            BeginInvoke(new Action(ShowDone));
        }

        private void ShowDone()
        {
            _progressBar.Style = ProgressBarStyle.Continuous;
            _progressBar.Value = 100;

            if (_installSuccess)
            {
                _lblDoneTitle.Text      = "Installation Complete!";
                _lblDoneTitle.ForeColor = Color.FromArgb(0, 128, 0);
                _lblDoneDetail.Text     =
                    "SA-US ERP v2.5.0 has been installed to:\n" + _installDir +
                    "\n\nDesktop and Start Menu shortcuts have been created for the installed components.";
                _btnOpenFolder.Enabled = true;
            }
            else
            {
                _lblDoneTitle.Text      = "Installation Failed";
                _lblDoneTitle.ForeColor = Color.DarkRed;
                _lblDoneDetail.Text     =
                    "The installation did not complete successfully.\n" +
                    "Review the log on the previous step for error details.\n\n" +
                    "You may run the installer again or contact SA Ultimate Solutions for support.";
                _btnOpenFolder.Enabled = false;
                _btnViewLog.Visible    = true;
            }

            GoToPage(4);
        }

        // ── Helpers ───────────────────────────────────────────────────────────

        private void Log(string text, Color? color = null)
        {
            if (InvokeRequired) { BeginInvoke(new Action(() => Log(text, color))); return; }
            _rtbLog.SelectionStart  = _rtbLog.TextLength;
            _rtbLog.SelectionLength = 0;
            _rtbLog.SelectionColor  = color ?? Color.FromArgb(212, 212, 212);
            _rtbLog.AppendText(text + "\n");
            _rtbLog.ScrollToCaret();
        }

        private static void ExtractRes(string name, string outPath)
        {
            using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
            {
                if (s == null) throw new InvalidOperationException("Missing embedded resource: " + name);
                using (var f = File.Create(outPath)) s.CopyTo(f);
            }
        }

        private static string GetExistingInstallDir()
        {
            try
            {
                using (var key = Registry.CurrentUser.OpenSubKey(
                    @"Software\Microsoft\Windows\CurrentVersion\Uninstall\SA-US ERP"))
                {
                    if (key != null)
                    {
                        var loc = key.GetValue("InstallLocation") as string;
                        if (!string.IsNullOrEmpty(loc) && Directory.Exists(loc)) return loc;
                    }
                }
            }
            catch { }
            var def = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs", "SA-US ERP");
            return Directory.Exists(def) ? def : null;
        }

        private static Label Title(string text, int x, int y)
        {
            return new Label { Text = text, Font = new Font("Segoe UI", 13, FontStyle.Bold),
                ForeColor = Color.FromArgb(24, 103, 192), AutoSize = true, Location = new Point(x, y) };
        }

        private static Label BodyLabel(string text, int x, int y, int width)
        {
            return new Label { Text = text, Font = new Font("Segoe UI", 10), AutoSize = false,
                Size = new Size(width, 160), Location = new Point(x, y) };
        }

        private static Label SmallLabel(string text, int x, int y)
        {
            return new Label { Text = text, Font = new Font("Segoe UI", 10), AutoSize = true, Location = new Point(x, y) };
        }

        private static RadioButton Radio(string text, int x, int y)
        {
            return new RadioButton { Text = text, Font = new Font("Segoe UI", 10), AutoSize = true, Location = new Point(x, y) };
        }
    }
}
