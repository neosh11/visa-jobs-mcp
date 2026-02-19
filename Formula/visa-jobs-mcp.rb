class VisaJobsMcp < Formula
  include Language::Python::Virtualenv

  desc "MCP server for finding visa-sponsoring jobs"
  homepage "https://github.com/<your-org>/visa-jobs-mcp"
  license "MIT"
  head "https://github.com/<your-org>/visa-jobs-mcp.git", branch: "main"

  depends_on "python@3.12"

  def install
    venv = virtualenv_create(libexec, "python3.12")
    venv.pip_install buildpath
    bin.install_symlink libexec/"bin/visa-jobs-mcp"
    bin.install_symlink libexec/"bin/visa-jobs-pipeline"
  end

  test do
    output = shell_output("#{bin}/visa-jobs-pipeline --help")
    assert_match "Run internal DOL data pipeline", output
  end
end
