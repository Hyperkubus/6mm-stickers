{
  description = "6mm IDF sticker generator — Python dev environment";

  inputs.nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1.*.tar.gz";

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forEachSupportedSystem = f: nixpkgs.lib.genAttrs supportedSystems (system: f {
        pkgs = import nixpkgs { inherit system; };
      });
    in
    {
      devShells = forEachSupportedSystem ({ pkgs }: {
        default = pkgs.mkShell {
          venvDir = ".venv";
          packages = with pkgs; [
            python312
            librsvg  # rsvg-convert, used by preview.py
          ] ++ (with pkgs.python312Packages; [
            pip
            venvShellHook
          ]);
          postVenvCreation = ''
            pip install -r requirements.txt
          '';
        };
      });
    };
}
