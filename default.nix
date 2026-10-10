{ lib
, python3Packages
, bubblewrap
, git
, makeWrapper
, callPackage
, agy ? callPackage ./agy.nix { }
}:

python3Packages.buildPythonApplication {
  pname = "infapla";
  version = "0.1.0";
  format = "pyproject";

  src = ./.;

  nativeBuildInputs = [
    python3Packages.setuptools
    makeWrapper
  ];

  propagatedBuildInputs = [
    python3Packages.flask
  ];

  postInstall = ''
    mkdir -p $out/share/infapla
    cp run-agy-sandboxed.sh $out/share/infapla/run-agy-sandboxed.sh
    chmod +x $out/share/infapla/run-agy-sandboxed.sh
  '';

  postFixup = ''
    wrapProgram $out/bin/infapla \
      --prefix PATH : ${lib.makeBinPath [ bubblewrap git agy ]} \
      --set-default INFAPLA_SANDBOX_SCRIPT "$out/share/infapla/run-agy-sandboxed.sh" \
      --set-default AGY_BIN "${agy}/bin/agy"
  '';

  passthru = {
    inherit agy;
  };

  meta = with lib; {
    description = "InFaPla - Intelligent Family Planner";
    homepage = "https://github.com/lluki/infapla";
    mainProgram = "infapla";
  };
}
