class OllamaFacade < Formula
  include Language::Python::Virtualenv

  desc "Run Claude Max as a local Ollama server on your network"
  homepage "https://github.com/travis-burmaster/ollama-facade"
  url "https://github.com/travis-burmaster/ollama-facade/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "4d5ebeca52f82c88a9ef202827014c7628b76d392d38579b81d120a64de45634"
  license "MIT"

  depends_on "python@3.12"

  resource "fastapi" do
    url "https://files.pythonhosted.org/packages/source/f/fastapi/fastapi-0.115.12.tar.gz"
    sha256 "1e2c2a2646905f9e83d32f04a3f86aff8a5a542a0a37f8827b4a6a64157a97e8"
  end

  resource "uvicorn" do
    url "https://files.pythonhosted.org/packages/source/u/uvicorn/uvicorn-0.34.0.tar.gz"
    sha256 "404ca8f0a4e7b09e2eeaaf5cd5df3f1720abe6762b4e02fe01d88825b0ceea50"
  end

  resource "httpx" do
    url "https://files.pythonhosted.org/packages/source/h/httpx/httpx-0.28.1.tar.gz"
    sha256 "75e98c5f16b0f35b567856f597f06ff2270a374470a5c2392242528e3e3e42fc"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/source/P/PyYAML/PyYAML-6.0.2.tar.gz"
    sha256 "d584d9ec91ad65861cc08d42e834324ef890a082e591037abe114850ff7bbc3e"
  end

  resource "curl-cffi" do
    url "https://files.pythonhosted.org/packages/source/c/curl_cffi/curl_cffi-0.7.4.tar.gz"
    sha256 "PLACEHOLDER_CURL_CFFI_SHA256"
  end

  def install
    virtualenv_install_with_resources
  end

  service do
    run [opt_bin/"ollama-facade", "start"]
    keep_alive true
    log_path var/"log/ollama-facade.log"
    error_log_path var/"log/ollama-facade.log"
    working_dir var
  end

  def caveats
    <<~EOS
      ollama-facade exposes Claude Max as a local Ollama server on port 11434.

      Before starting, create your config:
        ollama-facade config init

      Then edit ~/.ollama-facade/config.yaml to point at your claude-oauth-proxy:
        primary_url: "http://127.0.0.1:8319/v1"

      Start in the foreground:
        ollama-facade start

      Start as a background service:
        ollama-facade start --daemon

      Or use Homebrew services (launchd on macOS):
        brew services start ollama-facade

      Connect any Ollama-compatible client to:
        http://localhost:11434

      Full docs: https://github.com/travis-burmaster/ollama-facade
    EOS
  end

  test do
    assert_match "usage", shell_output("#{bin}/ollama-facade --help", 0)
  end
end
