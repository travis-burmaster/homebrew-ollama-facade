class OllamaFacade < Formula
  include Language::Python::Virtualenv

  desc "Run Claude Max as a local Ollama server on your network"
  homepage "https://github.com/travis-burmaster/homebrew-ollama-facade"
  url "https://github.com/travis-burmaster/homebrew-ollama-facade/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "a404bc4f587f1110fde8adc9817412c3958a9c3ef84e15571c728e22f5f00781"
  license "MIT"

  depends_on "python@3.12"

  resource "fastapi" do
    url "https://files.pythonhosted.org/packages/source/f/fastapi/fastapi-0.115.12.tar.gz"
    sha256 "1e2c2a2646905f9e83d32f04a3f86aff4a286669c6c950ca95b5fd68c2602681"
  end

  resource "uvicorn" do
    url "https://files.pythonhosted.org/packages/source/u/uvicorn/uvicorn-0.34.0.tar.gz"
    sha256 "404051050cd7e905de2c9a7e61790943440b3416f49cb409f965d9dcd0fa73e9"
  end

  resource "httpx" do
    url "https://files.pythonhosted.org/packages/source/h/httpx/httpx-0.28.1.tar.gz"
    sha256 "75e98c5f16b0f35b567856f597f06ff2270a374470a5c2392242528e3e3e42fc"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/54/ed/79a089b6be93607fa5cdaedf301d7dfb23af5f25c398d5ead2525b063e17/pyyaml-6.0.2.tar.gz"
    sha256 "d584d9ec91ad65861cc08d42e834324ef890a082e591037abe114850ff7bbc3e"
  end

  resource "curl-cffi" do
    url "https://files.pythonhosted.org/packages/source/c/curl_cffi/curl_cffi-0.7.4.tar.gz"
    sha256 "37a2c8ec77b9914b0c14c74f604991751948d9d5def58fcddcbe73e3b62111c1"
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

      Full docs: https://github.com/travis-burmaster/homebrew-ollama-facade
    EOS
  end

  test do
    assert_match "usage", shell_output("#{bin}/ollama-facade --help", 0)
  end
end
