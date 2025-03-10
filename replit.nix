{pkgs}: {
  deps = [
    pkgs.libxcrypt
    pkgs.openssl
    pkgs.glibcLocales
    pkgs.postgresql
  ];
}
