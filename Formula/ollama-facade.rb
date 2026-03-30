class OllamaFacade < Formula
  include Language::Python::Virtualenv

  desc "Run Claude Max as a local Ollama server on your network"
  homepage "https://github.com/travis-burmaster/homebrew-ollama-facade"
  url "https://github.com/travis-burmaster/homebrew-ollama-facade/archive/refs/tags/v2.0.3.tar.gz"
  sha256 "4959237042375fb0a7d78e0cbfc669620ff2704a5396504bee5370db75e1075d"
  license "MIT"

  depends_on "python@3.12"

  resource "certifi" do
    url "https://files.pythonhosted.org/packages/38/fc/bce832fd4fd99766c04d1ee0eead6b0ec6486fb100ae5e74c1d91292b982/certifi-2025.1.31-py3-none-any.whl"
    sha256 "ca78db4565a652026a4db2bcdf68f2fb589ea80d0be70e03929ed730746b84fe"
  end

  resource "idna" do
    url "https://files.pythonhosted.org/packages/76/c6/c88e154df9c4e1a2a66ccf0005a88dfb2650c1dffb6f5ce603dfbd452ce3/idna-3.10-py3-none-any.whl"
    sha256 "946d195a0d259cbba61165e88e65941f16e9b36ea6ddb97f00452bae8b1287d3"
  end

  resource "sniffio" do
    url "https://files.pythonhosted.org/packages/e9/44/75a9c9421471a6c4805dbf2356f7c181a29c1879239abab1ea2cc8f38b40/sniffio-1.3.1-py3-none-any.whl"
    sha256 "2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2"
  end

  resource "anyio" do
    url "https://files.pythonhosted.org/packages/a1/ee/48ca1a7c89ffec8b6a0c5d02b89c305671d5ffd8d3c94acf8b8c408575bb/anyio-4.9.0-py3-none-any.whl"
    sha256 "9f76d541cad6e36af7beb62e978876f3b41e3e04f2c1fbf0884604c0a9c4d93c"
  end

  resource "h11" do
    url "https://files.pythonhosted.org/packages/95/04/ff642e65ad6b90db43e668d70ffb6736436c7ce41fcc549f4e9472234127/h11-0.14.0-py3-none-any.whl"
    sha256 "e3fe4ac4b851c468cc8363d500db52c2ead036020723024a109d37346efaa761"
  end

  resource "httpcore" do
    url "https://files.pythonhosted.org/packages/7e/f5/f66802a942d491edb555dd61e3a9961140fd64c90bce1eafd741609d334d/httpcore-1.0.9-py3-none-any.whl"
    sha256 "2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55"
  end

  resource "httpx" do
    url "https://files.pythonhosted.org/packages/source/h/httpx/httpx-0.28.1.tar.gz"
    sha256 "75e98c5f16b0f35b567856f597f06ff2270a374470a5c2392242528e3e3e42fc"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/7e/d4/7ebdbd03970677812aac39c869717059dbb71a4cfc033ca6e5221787892c/click-8.1.8-py3-none-any.whl"
    sha256 "63c132bbbed01578a06712a2d1f497bb62d9c1c0d329b7903a866228027263b2"
  end

  resource "annotated-types" do
    url "https://files.pythonhosted.org/packages/78/b6/6307fbef88d9b5ee7421e68d78a9f162e0da4900bc5f5793f6d3d0e34fb8/annotated_types-0.7.0-py3-none-any.whl"
    sha256 "1f02e8b43a8fbbc3f3e0d4f0f4bfc8131bcb4eebe8849b8e5c773f3a1c582a53"
  end

  resource "starlette" do
    url "https://files.pythonhosted.org/packages/a0/4b/528ccf7a982216885a1ff4908e886b8fb5f19862d1962f56a3fce2435a70/starlette-0.46.1-py3-none-any.whl"
    sha256 "77c74ed9d2720138b25875133f3a2dae6d854af2ec37dceb56aef370c1d8a227"
  end

  resource "typing-extensions" do
    url "https://files.pythonhosted.org/packages/18/67/36e9267722cc04a6b9f15c7f3441c2363321a3ea07da7ae0c0707beb2a9c/typing_extensions-4.15.0-py3-none-any.whl"
    sha256 "f0fa19c6845758ab08074a0cfa8b7aecb71c999ca73d62883bc25cc018c4e548"
  end

  resource "typing-inspection" do
    url "https://files.pythonhosted.org/packages/dc/9b/47798a6c91d8bdb567fe2698fe81e0c6b7cb7ef4d13da4114b41d239f65d/typing_inspection-0.4.2-py3-none-any.whl"
    sha256 "4ed1cacbdc298c220f1bd249ed5287caa16f34d44ef4e9c3d0cbad5b521545e7"
  end

  resource "pycparser" do
    url "https://files.pythonhosted.org/packages/0c/c3/44f3fbbfa403ea2a7c779186dc20772604442dde72947e7d01069cbe98e3/pycparser-3.0-py3-none-any.whl"
    sha256 "b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/54/ed/79a089b6be93607fa5cdaedf301d7dfb23af5f25c398d5ead2525b063e17/pyyaml-6.0.2.tar.gz"
    sha256 "d584d9ec91ad65861cc08d42e834324ef890a082e591037abe114850ff7bbc3e"
  end

  resource "pydantic" do
    url "https://files.pythonhosted.org/packages/bf/c2/0f3baea344d0b15e35cb3e04ad5b953fa05106b76efbf4c782a3f47f22f5/pydantic-2.11.2-py3-none-any.whl"
    sha256 "7f17d25846bcdf89b670a86cdfe7b29a9f1c9ca23dee154221c9aa81845cfca7"
  end

  resource "uvicorn" do
    url "https://files.pythonhosted.org/packages/source/u/uvicorn/uvicorn-0.34.0.tar.gz"
    sha256 "404051050cd7e905de2c9a7e61790943440b3416f49cb409f965d9dcd0fa73e9"
  end

  resource "fastapi" do
    url "https://files.pythonhosted.org/packages/source/f/fastapi/fastapi-0.115.12.tar.gz"
    sha256 "1e2c2a2646905f9e83d32f04a3f86aff4a286669c6c950ca95b5fd68c2602681"
  end

  def install
    virtualenv_install_with_resources

    # Install native extension packages via pip (these have C extensions that must
    # be installed as pre-built wheels matching the target platform).
    # virtualenv_install_with_resources uses --without-pip, so use the formula
    # Python's pip with --python= to target the venv.
    pip = Formula["python@3.12"].opt_libexec/"bin/pip"
    venv_python = libexec/"bin/python"
    system pip, "--python=#{venv_python}", "install", "--no-deps", "pydantic-core==2.33.1"
    # cffi provides _cffi_backend (native C extension) required by curl-cffi at runtime.
    # pycparser (already installed as a resource above) is cffi's only dependency.
    system pip, "--python=#{venv_python}", "install", "cffi==2.0.0"
    system pip, "--python=#{venv_python}", "install", "--no-deps", "curl-cffi==0.7.4"
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

      Quick start:
        ollama-facade config --init
        # Add your OAuth token to ~/.ollama-facade/config.yaml:
        #   accounts:
        #     - token: "sk-ant-oat01-..."
        # Get your token by running: claude setup-token
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
