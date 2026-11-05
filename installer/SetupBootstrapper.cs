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

        // Page 3 — DB Config
        private RadioButton _rbSQLite, _rbMySQL;
        private Panel  _mysqlPanel;
        private TextBox _txtDbHost, _txtDbPort, _txtDbName;
        private TextBox _txtDbRootUser, _txtDbRootPass;
        private TextBox _txtDbAppUser, _txtDbAppPass;

        // Page 4 — Progress
        private ProgressBar _progressBar;
        private RichTextBox _rtbLog;

        // Page 5 — Done
        private Label _lblDoneTitle, _lblDoneDetail;
        private Button _btnOpenFolder, _btnViewLog;

        // Page 4 — title ref so uninstall can relabel it
        private Label _lblProgressTitle;

        private bool _installSuccess;
        private bool _uninstallMode;
        private bool _updateMode;
        private string _installDir;
        private string _existingDir;
        private string _installedVersion;

        // Page 1 — extra options only when existing install found
        private RadioButton _rbUpdate;
        private RadioButton _rbUninstall;

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
            _tab.TabPages.Add(BuildPage3_DBConfig());
            _tab.TabPages.Add(BuildPage4_Progress());
            _tab.TabPages.Add(BuildPage5_Done());

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
            p.Controls.Add(MakeTitle("Welcome to SA-US ERP Setup v2.9.0", 24, 18));
            p.Controls.Add(MakeLabel(
                "This wizard will install SA-US ERP on your computer.\r\n\r\n" +
                "SA-US ERP is a business management system that includes:\r\n\r\n" +
                "  \u2022  Server \u2014 runs on the main office PC  (SQLite database (no setup required))\r\n" +
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
                _installedVersion = GetInstalledVersion();
                string updateLabel = string.IsNullOrEmpty(_installedVersion)
                    ? "Update SA-US ERP to v2.9.0  (recommended)  \u2014  preserves database & config"
                    : "Update from v" + _installedVersion + " to v2.9.0  (recommended)  \u2014  preserves database & config";

                p.Controls.Add(MakeTitle("Existing Installation Found", 24, 18));
                p.Controls.Add(MakeLabel(
                    "SA-US ERP is already installed at:\r\n" + _existingDir +
                    "\r\n\r\nChoose an option below:",
                    24, 62, 520, 52));

                _rbUpdate = MakeRadio(updateLabel, 40, 120);
                _rbUpdate.ForeColor = Color.FromArgb(0, 120, 0);
                _rbUpdate.Checked = true;

                var sep1 = new Panel { BackColor = Color.FromArgb(210, 210, 210), Bounds = new Rectangle(24, 154, 520, 1) };
                p.Controls.Add(MakeSmall("Reinstall / Repair:", 24, 162));

                _rbServer = MakeRadio("Server only  \u2014  main office PC",                        40, 182);
                _rbClient = MakeRadio("Client only  \u2014  staff PC connecting over the network",   40, 208);
                _rbBoth   = MakeRadio("Both server and client",                                      40, 234);

                var sep2 = new Panel { BackColor = Color.FromArgb(210, 210, 210), Bounds = new Rectangle(24, 262, 520, 1) };
                _rbUninstall = MakeRadio("Remove / Uninstall SA-US ERP from this computer", 40, 272);
                _rbUninstall.ForeColor = Color.DarkRed;

                p.Controls.AddRange(new Control[] { _rbUpdate, sep1, _rbServer, _rbClient, _rbBoth, sep2, _rbUninstall });
            }
            else
            {
                // Fresh install
                p.Controls.Add(MakeTitle("Choose Installation Type", 24, 18));
                p.Controls.Add(MakeLabel("Choose what to install on this machine:", 24, 66, 520, 26));

                _rbServer = MakeRadio("Server only  \u2014  main office PC",                        40, 112);
                _rbClient = MakeRadio("Client only  \u2014  staff PC connecting over the network",   40, 144);
                _rbBoth   = MakeRadio("Both server and client  (recommended for single-PC setup)",   40, 176);
                _rbBoth.Checked = true;
                p.Controls.AddRange(new Control[] { _rbServer, _rbClient, _rbBoth });
            }
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

        private TabPage BuildPage3_DBConfig()
        {
            var p = NewPage();
            p.Controls.Add(MakeTitle("Database Configuration", 24, 18));
            p.Controls.Add(MakeLabel(
                "Choose where the server stores its data. SQLite requires no setup and is recommended for most offices.",
                24, 66, 520, 36));

            _rbSQLite = MakeRadio("SQLite  \u2014  built-in database, no setup required  (recommended)", 40, 110);
            _rbSQLite.Checked = true;
            _rbMySQL  = MakeRadio("MySQL  \u2014  use an existing MySQL / MariaDB server", 40, 132);

            _mysqlPanel = new Panel
            {
                Bounds  = new Rectangle(24, 162, 530, 158),
                Visible = false
            };

            Action toggleMySQL = () => _mysqlPanel.Visible = _rbMySQL.Checked;
            _rbMySQL.CheckedChanged  += (s, e2) => toggleMySQL();
            _rbSQLite.CheckedChanged += (s, e2) => toggleMySQL();

            // Row 0 — host + port
            _mysqlPanel.Controls.Add(MakeSmall2("Host:", 0, 2));
            _txtDbHost = MakeTxt("localhost", 50, 0, 174);
            _mysqlPanel.Controls.Add(_txtDbHost);
            _mysqlPanel.Controls.Add(MakeSmall2("Port:", 234, 2));
            _txtDbPort = MakeTxt("3306", 274, 0, 70);
            _mysqlPanel.Controls.Add(_txtDbPort);

            // Row 1 — database name
            _mysqlPanel.Controls.Add(MakeSmall2("Database name:", 0, 30));
            _txtDbName = MakeTxt("sa_us_erp", 112, 28, 240);
            _mysqlPanel.Controls.Add(_txtDbName);

            // Row 2 — root credentials
            _mysqlPanel.Controls.Add(MakeSmall2("MySQL admin user:", 0, 60));
            _txtDbRootUser = MakeTxt("root", 130, 58, 120);
            _mysqlPanel.Controls.Add(_txtDbRootUser);
            _mysqlPanel.Controls.Add(MakeSmall2("Admin password:", 260, 60));
            _txtDbRootPass = MakeTxt("", 370, 58, 140);
            _txtDbRootPass.PasswordChar = '\u25CF';
            _mysqlPanel.Controls.Add(_txtDbRootPass);

            // Row 3 — app credentials
            _mysqlPanel.Controls.Add(MakeSmall2("App username:", 0, 90));
            _txtDbAppUser = MakeTxt("sa_us_user", 100, 88, 140);
            _mysqlPanel.Controls.Add(_txtDbAppUser);
            _mysqlPanel.Controls.Add(MakeSmall2("App password:", 250, 90));
            _txtDbAppPass = MakeTxt("", 350, 88, 150);
            _txtDbAppPass.PasswordChar = '\u25CF';
            _mysqlPanel.Controls.Add(_txtDbAppPass);

            // Note
            var note = new Label
            {
                Text      = "Admin credentials are only used to create the database and are not stored.",
                Font      = new Font("Segoe UI", 8.5f),
                ForeColor = Color.FromArgb(100, 100, 100),
                AutoSize  = false,
                Size      = new Size(520, 22),
                Location  = new Point(0, 124)
            };
            _mysqlPanel.Controls.Add(note);

            p.Controls.AddRange(new Control[] { _rbSQLite, _rbMySQL, _mysqlPanel });
            return p;
        }

        private TabPage BuildPage4_Progress()
        {
            var p = NewPage();
            _lblProgressTitle = MakeTitle("Installing SA-US ERP...", 24, 18);
            p.Controls.Add(_lblProgressTitle);

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

        private TabPage BuildPage5_Done()
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

        private bool IsServerInstall()
        {
            if (_updateMode || _uninstallMode) return false;
            if (_rbBoth   != null && _rbBoth.Checked)   return true;
            if (_rbServer != null && _rbServer.Checked) return true;
            return false;
        }

        private void ShowPage(int page)
        {
            _tab.SelectedIndex = page;

            _btnBack.Enabled   = page > 0 && page < 4;
            _btnCancel.Visible = page < 5;
            _btnNext.Visible   = true;
            _btnNext.Enabled   = true;

            switch (page)
            {
                case 0:
                case 1:
                    _btnNext.Text = "Next >";
                    break;
                case 2:
                    _btnNext.Text = IsServerInstall() ? "Next >" : "Install";
                    break;
                case 3:
                    _btnNext.Text = "Install";
                    break;
                case 4:
                    _btnBack.Enabled   = false;
                    _btnNext.Enabled   = false;
                    _btnCancel.Enabled = false;
                    if (_uninstallMode && _lblProgressTitle != null)
                        _lblProgressTitle.Text = "Removing SA-US ERP...";
                    else if (_updateMode && _lblProgressTitle != null)
                        _lblProgressTitle.Text = "Updating SA-US ERP...";
                    StartInstall();
                    break;
                case 5:
                    _btnBack.Enabled = false;
                    _btnNext.Text    = "Finish";
                    break;
            }
        }

        private void OnNext(object s, EventArgs e)
        {
            int page = _tab.SelectedIndex;
            if (page == 5) { ExitCode = _installSuccess ? 0 : 1; Close(); return; }

            // Update path: skip directory + DB config, go straight to progress
            if (page == 1 && _rbUpdate != null && _rbUpdate.Checked)
            {
                _updateMode = true;
                ShowPage(4);
                return;
            }

            // Uninstall path: skip directory + DB config, go straight to progress
            if (page == 1 && _rbUninstall != null && _rbUninstall.Checked)
            {
                _uninstallMode = true;
                ShowPage(4);
                return;
            }

            if (page == 2 && string.IsNullOrWhiteSpace(_txtDir.Text))
            {
                MessageBox.Show("Please choose an installation folder.", "Required",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            // Client-only install: skip DB config page, go straight to progress
            if (page == 2 && !IsServerInstall())
            {
                ShowPage(4);
                return;
            }

            // DB Config page: validate MySQL fields if MySQL selected
            if (page == 3 && _rbMySQL != null && _rbMySQL.Checked)
            {
                if (string.IsNullOrWhiteSpace(_txtDbHost.Text) ||
                    string.IsNullOrWhiteSpace(_txtDbPort.Text) ||
                    string.IsNullOrWhiteSpace(_txtDbName.Text) ||
                    string.IsNullOrWhiteSpace(_txtDbRootPass.Text) ||
                    string.IsNullOrWhiteSpace(_txtDbAppUser.Text) ||
                    string.IsNullOrWhiteSpace(_txtDbAppPass.Text))
                {
                    MessageBox.Show("Please fill in all MySQL fields.", "Required",
                        MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
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
            if (_tab.SelectedIndex == 4) { e.Cancel = true; return; }
            base.OnFormClosing(e);
        }

        // ── Install ───────────────────────────────────────────────────────────

        private void StartInstall()
        {
            _installDir = (_uninstallMode || _updateMode) ? _existingDir : _txtDir.Text.Trim();
            new Thread(RunInstall) { IsBackground = true }.Start();
        }

        private void RunInstall()
        {
            if (_uninstallMode) { RunUninstall(); return; }

            string tempRoot = Path.Combine(Path.GetTempPath(),
                "SA-US-ERP-" + Guid.NewGuid().ToString("N").Substring(0, 10));
            try
            {
                Log("SA-US ERP Installer v2.9.0", Color.FromArgb(110, 185, 255));
                Log(new string('-', 44), Color.FromArgb(70, 70, 70));
                Log("Extracting installer resources...");

                Directory.CreateDirectory(tempRoot);
                ExtractRes("install.cmd", Path.Combine(tempRoot, "install.cmd"));
                ExtractRes("install.ps1", Path.Combine(tempRoot, "install.ps1"));
                ExtractRes("payload.zip", Path.Combine(tempRoot, "payload.zip"));

                Log("Resources extracted.", Color.FromArgb(100, 210, 100));

                string mode = "both";
                if (_updateMode)
                {
                    // Auto-detect which components are installed
                    bool hasServer = Directory.Exists(Path.Combine(_installDir, "server"));
                    bool hasClient = Directory.Exists(Path.Combine(_installDir, "client"));
                    if (hasServer && !hasClient)      mode = "server";
                    else if (hasClient && !hasServer) mode = "client";
                    else                              mode = "both";
                    Log("Detected installed components: " + mode);
                }
                else
                {
                    Invoke(new Action(() =>
                    {
                        if (_rbServer.Checked)      mode = "server";
                        else if (_rbClient.Checked) mode = "client";
                        else                        mode = "both";
                    }));
                }

                Log(_updateMode ? "Mode      : update (" + mode + ")" : "Mode      : " + mode);
                Log("Directory : " + _installDir);
                Log("");
                Log(_updateMode ? "Starting update script..." : "Starting install script...", Color.FromArgb(110, 185, 255));

                string dbType = "sqlite";
                string dbHost = "localhost", dbPort = "3306", dbName = "sa_us_erp";
                string dbRootUser = "root", dbRootPass = "", dbAppUser = "sa_us_user", dbAppPass = "";
                if (!_updateMode)
                {
                    Invoke(new Action(() =>
                    {
                        if (_rbMySQL != null && _rbMySQL.Checked)
                        {
                            dbType     = "mysql";
                            dbHost     = _txtDbHost.Text.Trim();
                            dbPort     = _txtDbPort.Text.Trim();
                            dbName     = _txtDbName.Text.Trim();
                            dbRootUser = _txtDbRootUser.Text.Trim();
                            dbRootPass = _txtDbRootPass.Text;
                            dbAppUser  = _txtDbAppUser.Text.Trim();
                            dbAppPass  = _txtDbAppPass.Text;
                        }
                    }));
                }

                var psArgs = string.Format(
                    "-NoProfile -ExecutionPolicy Bypass -File \"{0}\"" +
                    " -InstallMode \"{1}\" -InstallDir \"{2}\" -SkipMaintenanceDialog" +
                    " -DbType \"{3}\" -DbHost \"{4}\" -DbPort \"{5}\" -DbName \"{6}\"" +
                    " -DbRootUser \"{7}\" -DbRootPass \"{8}\" -DbAppUser \"{9}\" -DbAppPass \"{10}\"",
                    Path.Combine(tempRoot, "install.ps1"), mode, _installDir,
                    dbType, dbHost, dbPort, dbName, dbRootUser, dbRootPass, dbAppUser, dbAppPass);
                if (_updateMode)
                    psArgs += " -UpdateMode";

                var psi = new ProcessStartInfo
                {
                    FileName  = "powershell.exe",
                    Arguments = psArgs,
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

        private void RunUninstall()
        {
            Log("SA-US ERP Uninstaller v2.9.0", Color.FromArgb(110, 185, 255));
            Log(new string('-', 44), Color.FromArgb(70, 70, 70));
            Log("Removing SA-US ERP from: " + _installDir);
            Log("");

            var script = Path.Combine(_installDir, "uninstall.ps1");
            if (!File.Exists(script))
            {
                Log("Uninstaller script not found: " + script, Color.FromArgb(255, 100, 100));
                Log("Please remove the folder manually: " + _installDir, Color.FromArgb(255, 165, 80));
                _installSuccess = false;
            }
            else
            {
                try
                {
                    var psi = new ProcessStartInfo
                    {
                        FileName  = "powershell.exe",
                        Arguments = string.Format(
                            "-NoProfile -ExecutionPolicy Bypass -File \"{0}\"" +
                            " -InstallDir \"{1}\" -Quiet -KeepConfig",
                            script, _installDir),
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
                }
                catch (Exception ex)
                {
                    Log("Error: " + ex.Message, Color.FromArgb(255, 100, 100));
                    _installSuccess = false;
                }
            }

            Log("");
            Log(_installSuccess
                ? "SA-US ERP removed successfully."
                : "Uninstallation failed (see log above).",
                _installSuccess ? Color.FromArgb(100, 210, 100) : Color.FromArgb(255, 100, 100));

            BeginInvoke(new Action(ShowDone));
        }

        private void ShowDone()
        {
            _progressBar.Style = ProgressBarStyle.Continuous;
            _progressBar.Value = 100;

            if (_uninstallMode)
            {
                _btnOpenFolder.Visible = false;
                if (_installSuccess)
                {
                    _lblDoneTitle.Text      = "Uninstallation Complete";
                    _lblDoneTitle.ForeColor = Color.FromArgb(0, 140, 0);
                    _lblDoneDetail.Text     =
                        "SA-US ERP has been removed from your computer.\r\n\r\n" +
                        "Configuration files were preserved in your AppData folder.\r\n\r\n" +
                        "You may close this window.";
                }
                else
                {
                    _lblDoneTitle.Text      = "Uninstallation Failed";
                    _lblDoneTitle.ForeColor = Color.DarkRed;
                    _lblDoneDetail.Text     =
                        "The uninstall did not complete successfully.\r\n" +
                        "Click View Installation Log to see error details.";
                    _btnViewLog.Visible = true;
                }
            }
            else if (_updateMode)
            {
                if (_installSuccess)
                {
                    _lblDoneTitle.Text      = "Update Complete!";
                    _lblDoneTitle.ForeColor = Color.FromArgb(0, 140, 0);
                    _lblDoneDetail.Text     =
                        "SA-US ERP has been updated to v2.9.0 at:\r\n" + _installDir +
                        "\r\n\r\nYour database and configuration files were preserved.\r\n" +
                        "A database backup was created in the server folder.";
                    _btnOpenFolder.Enabled  = true;
                }
                else
                {
                    _lblDoneTitle.Text      = "Update Failed";
                    _lblDoneTitle.ForeColor = Color.DarkRed;
                    _lblDoneDetail.Text     =
                        "The update did not complete successfully.\r\n" +
                        "Your existing installation was not modified.\r\n\r\n" +
                        "Click View Installation Log to see error details.";
                    _btnOpenFolder.Enabled  = false;
                    _btnViewLog.Visible     = true;
                }
            }
            else if (_installSuccess)
            {
                _lblDoneTitle.Text      = "Installation Complete!";
                _lblDoneTitle.ForeColor = Color.FromArgb(0, 140, 0);
                _lblDoneDetail.Text     =
                    "SA-US ERP v2.9.0 has been installed to:\r\n" + _installDir +
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

            ShowPage(5);
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

        private static string GetInstalledVersion()
        {
            try
            {
                using (var key = Registry.CurrentUser.OpenSubKey(
                    @"Software\Microsoft\Windows\CurrentVersion\Uninstall\SA-US ERP"))
                {
                    if (key != null) return key.GetValue("DisplayVersion") as string;
                }
            }
            catch { }
            return null;
        }

        private static string GetExistingInstallDir()
        {
            // 1. HKCU registry (written by install.ps1)
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

            // 2. HKLM registry (in case a previous version wrote there)
            try
            {
                using (var key = Registry.LocalMachine.OpenSubKey(
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

            // 3. Common install paths — look for actual app EXEs
            var candidates = new[]
            {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Programs", "SA-US ERP"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                    "SA-US ERP"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                    "SA-US ERP"),
            };

            foreach (var c in candidates)
            {
                if (Directory.Exists(c) && (
                    File.Exists(Path.Combine(c, "server", "SA_US_ERP_Server.exe")) ||
                    File.Exists(Path.Combine(c, "client", "SA_US_ERP_Client.exe"))))
                    return c;
            }

            return null;
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

        private static Label MakeSmall2(string text, int x, int y)
        {
            return new Label
            {
                Text     = text,
                Font     = new Font("Segoe UI", 9),
                AutoSize = true,
                Location = new Point(x, y + 3)
            };
        }

        private static TextBox MakeTxt(string def, int x, int y, int w)
        {
            return new TextBox
            {
                Text     = def,
                Font     = new Font("Segoe UI", 9.5f),
                Size     = new Size(w, 22),
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
