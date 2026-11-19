{
  description = "NixOS development shell for nf-pooled-cellpainting";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { nixpkgs, ... }:
    let
      pkgs = import nixpkgs { system = "x86_64-linux"; };
      nf-test-fhs = pkgs.buildFHSEnv {
        name = "nf-test-fhs";
        targetPkgs = pkgs: [ pkgs.pixi ];
        runScript = "pixi run --locked nf-test";
        # Run containers on the host, outside bubblewrap's user namespace.
        profile = ''
          export CONTAINER_HOST="unix://''${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/podman/podman.sock"
        '';
      };
    in
    {
      devShells.x86_64-linux.default = pkgs.mkShellNoCC {
        packages = [ pkgs.pixi nf-test-fhs ];
      };
    };
}
