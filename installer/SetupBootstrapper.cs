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
        // Fixed client dimensions — no DPI surprises from Size vs ClientSize
        private const int CW = 574;
        private const int CH = 450;
        private const int HDR_H  = 70;   // header band
        private const int BAR_H  = 52;   // button bar
        private const int PAGE_H = CH - HDR_H - BAR_H;  // 328 px of page content

        private TabControl _tab;
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
            ClientSize      = new Size(CW, CH);   // set client size directly
            FormBorderStyle = FormBorderStyle.FixedDialog;
            StartPosition   = FormStartPosition.CenterScreen;
            MaximizeBox     = false;
            MinimizeBox     = false;
            Font            = new Font("Segoe UI", 9.5f);
            BackColor       = Color.White;

            BuildForm();
            ShowPage(0);
        }

        // ── Build ─────────────────────────────────────────────────────────────

        private void BuildForm()
        {
            // 1. Header — explicit bounds, no docking
            var hdr = new Panel
            {
                BackColor = Color.FromArgb(24, 103, 192),
                Bounds    = new Rectangle(0, 0, CW, HDR_H)
            };
            hdr.Paint += (s, e) =>
            {
                var g = e.Graphics;
                g.DrawString("SA-US ERP Setup",
                    new Font("Segoe UI", 15, FontStyle.Bold),
                    Brushes.White, 20f, 8f);
                g.DrawString("SA Ultimate Solutions  —  Enterprise Resource Planning",
                    new Font("Segoe UI", 9),
                    new SolidBrush(Color.FromArgb(190, 225, 255)), 22f, 44f);
            };

            // 2. TabControl — explicit bounds, tabs hidden via ItemSize trick
            _tab = new TabControl
            {
                Bounds     = new Rectangle(0, HDR_H, CW, PAGE_H + 2),
                Appearance = TabAppearance.FlatButtons,
                ItemSize   = new Size(0, 1),
                SizeMode   = TabSizeMode.Fixed
            };
            _tab.TabPages.Add(BuildPage0_Welcome());
            _tab.TabPages.Add(BuildPage1_Mode());
            _tab.TabPages.Add(BuildPage2_Directory());
            _tab.TabPages.Add(BuildPage3_Progress());
            _tab.TabPages.Add(BuildPage4_Done());

            // 3. Separator line
            var sep = new Panel
            {
                BackColor = Color.FromArgb(210, 210, 210),
                Bounds    = new Rectangle(0, HDR_H + PAGE_H + 1, CW, 1)
            };

            // 4. Button bar — explicit bounds
            var bar = new Panel
            {
                BackColor = Color.FromArgb(245, 245, 245),
                Bounds    = new Rectangle(0, CH - BAR_H, CW, BAR_H)
            };

            int bx = CW - 12;
            _btnCancel = MakeBtn("Cancel",   bx - 96,       10);
            _btnNext   = MakeBtn("Next >",   bx - 96 - 106, 10);
            _btnBack   = MakeBtn("< Back",   bx - 96 - 106 - 106, 10);

            _btnNext.Click   += OnNext;
            _btnBack.Click   += (s, e) => ShowPage(_tab.SelectedIndex - 1);
            _btnCancel.Click += OnCancel;

            bar.Controls.AddRange(new Control[] { _btnBack, _btnNext, _btnCancel });

            Controls.AddRange(new Control[] { hdr, _tab, sep, bar });
        }

        private static Button MakeBtn(string text, int x, int y)
        {
            return new Button { Text = text, Size = new Size(96, 32), Location = new Point(x, y) };
        }

        // ── Pages ─────────────────────────────────────────────────────────────

        private TabPage NewPage()
        {
            return new TabPage { BackColor = Color.White, Padding = new Padding(0) };
        }

        private TabPage BuildPage0_Welcome()
        {
            var p = NewPage();
            p.Controls.Add(MakeTitle("Welcome to SA-US ERP Setup v2.6.1", 24, 18));
            p.Controls.Add(MakeLabel(
                "This wizard will install SA-US ERP on your computer.\r\n\r\n" +
                "SA-US ERP is a business management system that includes:\r\n\r\n" +
                "  \u2022  Server \u2014 runs on the main office PC  (MariaDB included, no internet needed)\r\n" +
                "  \u2022  Client \u2014 runs on any staff PC and connects to the server\r\n\r\n" +
                "Click Next to continue or Cancel to exit.",
                24, 66, 520, 210));
            return p;
        }

        private TabPage BuildPage1_Mode()
        {
            var p = NewPage();
            if (_existingDir != null)
            {
                p.Controls.Add(MakeTitle("Existing Installation Found", 24, 18));
                p.Controls.Add(MakeLabel(
                    "SA-US ERP is already installed at:\r\n" + _existingDir +
                    "\r\n\r\nChoose what to repair / reinstall:",
                    24, 66, 520, 80));
            }
            else
            {
                p.Controls.Add(MakeTitle("Choose Installation Type", 24, 18));
                p.Controls.Add(MakeLabel("Choose what to install on this machine:", 24, 66, 520, 26));
            }
            _rbServer = MakeRadio("Server only  \u2014  main office PC",                        40, 112);
            _rbClient = MakeRadio("Client only  \u2014  staff PC connecting over the network",   40, 144);
            _rbBoth   = MakeRadio("Both server and client  (recommended for single-PC setup)",   40, 176);
            _rbBoth.Checked = true;
            p.Controls.AddRange(new Control[] { _rbServer, _rbClient, _rbBoth });
            return p;
        }

        private TabPage BuildPage2_Directory()
        {
            var p = NewPage();
            p.Controls.Add(MakeTitle("Choose Install Location", 24, 18));
            p.Controls.Add(MakeLabel(
                "SA-US ERP will be installed to the folder below.\r\n" +
                "Click Browse to choose a different location.",
                24, 66, 520, 44));
            p.Controls.Add(MakeSmall("Destination folder:", 24, 128));

            var defPath = _existingDir ??
                Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Programs", "SA-US ERP");

            _txtDir = new TextBox
            {
                Text     = defPath,
                Font     = new Font("Segoe UI", 10),
                Size     = new Size(406, 26),
                Location = new Point(24, 150)
            };
            var btnBrowse = new Button { Text = "Browse...", Size = new Size(88, 26), Location = new Point(436, 150) };
            btnBrowse.Click += (s, e) =>
            {
                using (var dlg = new FolderBrowserDialog
                    { Description = "Choose install folder", SelectedPath = _txtDir.Text })
                {
                    if (dlg.ShowDialog() == DialogResult.OK)
                        _txtDir.Text = dlg.SelectedPath;
                }
            };
            p.Controls.AddRange(new Control[] { _txtDir, btnBrowse });
            return p;
        }

        private TabPage BuildPage3_Progress()
        {
            var p = NewPage();
            p.Controls.Add(MakeTitle("Installing SA-US ERP...", 24, 18));

            _progressBar = new ProgressBar
            {
                Style = ProgressBarStyle.Marquee,
                MarqueeAnimationSpeed = 25,
                Size     = new Size(524, 20),
                Location = new Point(24, 60)
            };

            _rtbLog = new RichTextBox
            {
                ReadOnly  = true,
                BackColor = Color.FromArgb(28, 28, 28),
                ForeColor = Color.FromArgb(212, 212, 212),
                Font      = new Font("Consolas", 8.5f),
                Size      = new Size(524, 220),
                Location  = new Point(24, 90),
                ScrollBars = RichTextBoxScrollBars.Vertical,
                WordWrap  = true
            };

            p.Controls.AddRange(new Control[] { _progressBar, _rtbLog });
            return p;
        }

        private TabPage BuildPage4_Done()
        {
            var p = NewPage();

            _lblDoneTitle = new Label
            {
                Font      = new Font("Segoe UI", 14, FontStyle.Bold),
                AutoSize  = true,
                Location  = new Point(24, 22)
            };
            _lblDoneDetail = new Label
            {
                Font      = new Font("Segoe UI", 10),
                AutoSize  = false,
                Size      = new Size(520, 120),
                Location  = new Point(24, 72)
            };
            _btnOpenFolder = new Button
            {
                Text     = "Open Install Folder",
                Size     = new Size(160, 34),
                Location = new Point(24, 204)
            };
            _btnOpenFolder.Click += (s, e) =>
            {
                if (!string.IsNullOrEmpty(_installDir) && Directory.Exists(_installDir))
                    Process.Start("explorer.exe", _installDir);
            };
            _btnViewLog = new Button
            {
                Text     = "View Installation Log",
                Size     = new Size(160, 34),
                Location = new Point(196, 204),
                Visible  = false
            };
            _btnViewLog.Click += (s, e) => ShowLogDialog();

            p.Controls.AddRange(new Control[] { _lblDoneTitle, _lblDoneDetail, _btnOpenFolder, _btnViewLog });
            return p;
        }

        // ── Navigation ────────────────────────────────────────────────────────

        private void ShowPage(int page)
        {
            _tab.SelectedIndex = page;

            _btnBack.Enabled   = page > 0 && page < 3;
            _btnCancel.Visible = page < 4;
            _btnNext.Visible   = true;
            _btnNext.Enabled   = true;

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
            int page = _tab.SelectedIndex;
            if (page == 4) { ExitCode = _installSuccess ? 0 : 1; Close(); return; }

            if (page == 2 && string.IsNullOrWhiteSpace(_txtDir.Text))
            {
                MessageBox.Show("Please choose an installation folder.", "Required",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            ShowPage(page + 1);
        }

        private void OnCancel(object s, EventArgs e)
        {
            if (MessageBox.Show("Are you sure you want to cancel?", "SA-US ERP Setup",
                    MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
            { ExitCode = 1; Close(); }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (_tab.SelectedIndex == 3) { e.Cancel = true; return; }
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
                Log("SA-US ERP Installer v2.6.1", Color.FromArgb(110, 185, 255));
                Log(new string('-', 44), Color.FromArgb(70, 70, 70));
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
                    proc.OutputDataReceived += (s, e2) =>
                        { if (e2.Data != null) Log(e2.Data); };
                    proc.ErrorDataReceived  += (s, e2) =>
                        { if (e2.Data != null) Log("[!] " + e2.Data, Color.FromArgb(255, 165, 80)); };
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
                Log(""); Log("FATAL: " + ex.Message, Color.FromArgb(255, 100, 100));
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
                _lblDoneTitle.ForeColor = Color.FromArgb(0, 140, 0);
                _lblDoneDetail.Text     =
                    "SA-US ERP v2.6.1 has been installed to:\r\n" + _installDir +
                    "\r\n\r\nShortcuts have been created on the Desktop and Start Menu.";
                _btnOpenFolder.Enabled  = true;
            }
            else
            {
                _lblDoneTitle.Text      = "Installation Failed";
                _lblDoneTitle.ForeColor = Color.DarkRed;
                _lblDoneDetail.Text     =
                    "The installation did not complete successfully.\r\n" +
                    "Click View Installation Log to see error details.\r\n\r\n" +
                    "You may run the installer again or contact SA Ultimate Solutions for support.";
                _btnOpenFolder.Enabled  = false;
                _btnViewLog.Visible     = true;
            }

            ShowPage(4);
        }

        private void ShowLogDialog()
        {
            var f = new Form
            {
                Text = "Installation Log \u2014 SA-US ERP", Size = new Size(620, 460),
                StartPosition = FormStartPosition.CenterParent,
                Font = new Font("Segoe UI", 9.5f), MinimizeBox = false
            };
            var rtb = new RichTextBox
            {
                Dock = DockStyle.Fill, ReadOnly = true,
                BackColor = Color.FromArgb(28, 28, 28),
                ForeColor = Color.FromArgb(212, 212, 212),
                Font = new Font("Consolas", 8.5f),
                Text = _rtbLog.Text,
                ScrollBars = RichTextBoxScrollBars.Vertical
            };
            f.Controls.Add(rtb);
            f.ShowDialog(this);
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
                if (s == null)
                    throw new InvalidOperationException("Missing embedded resource: " + name);
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

        private static Label MakeTitle(string text, int x, int y)
        {
            return new Label
            {
                Text      = text,
                Font      = new Font("Segoe UI", 13, FontStyle.Bold),
                ForeColor = Color.FromArgb(24, 103, 192),
                AutoSize  = true,
                Location  = new Point(x, y)
            };
        }

        private static Label MakeLabel(string text, int x, int y, int w, int h)
        {
            return new Label
            {
                Text      = text,
                Font      = new Font("Segoe UI", 10),
                AutoSize  = false,
                Size      = new Size(w, h),
                Location  = new Point(x, y)
            };
        }

        private static Label MakeSmall(string text, int x, int y)
        {
            return new Label
            {
                Text     = text,
                Font     = new Font("Segoe UI", 10),
                AutoSize = true,
                Location = new Point(x, y)
            };
        }

        private static RadioButton MakeRadio(string text, int x, int y)
        {
            return new RadioButton
            {
                Text     = text,
                Font     = new Font("Segoe UI", 10),
                AutoSize = true,
                Location = new Point(x, y)
            };
        }
    }
}
