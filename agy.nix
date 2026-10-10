{ stdenv, fetchurl, autoPatchelfHook }:

stdenv.mkDerivation rec {
  pname = "google-antigravity-cli";
  version = "1.3.3-5524738307653632";

  src = fetchurl {
    url = "https://storage.googleapis.com/antigravity-public/antigravity-cli/${version}/linux-x64/cli_linux_x64.tar.gz";
    hash = "sha512-q+Pd9c8w062qWGrPUFIhqhlwL1ynGvPIsfmxpZdr2OXBUcQeozs5xBZ10lhDRio+jDgsBU9YDp1+FoiRnTtREA==";
  };

  nativeBuildInputs = [ autoPatchelfHook ];

  sourceRoot = ".";

  installPhase = ''
    runHook preInstall
    mkdir -p $out/bin
    cp antigravity $out/bin/agy
    chmod +x $out/bin/agy
    runHook postInstall
  '';

  meta = {
    description = "Google Antigravity CLI (agy)";
    mainProgram = "agy";
  };
}
