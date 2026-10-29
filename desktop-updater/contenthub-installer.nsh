; Versioned installs are additive. NSIS must not move every old file to its
; temporary directory (which can be on another drive) before extracting.
!macro customRemoveFiles
  ${if} ${isUpdated}
    DetailPrint "Retaining existing program versions for update recovery."
  ${else}
    SetOutPath $TEMP
    ClearErrors
    CopyFiles /SILENT "$INSTDIR\ContentHub.exe" "$PLUGINSDIR\ContentHub-cleanup.exe"
    ${if} ${Errors}
      Abort "Please repair this installation before uninstalling. User data is retained."
    ${endif}
    ExecWait '"$PLUGINSDIR\ContentHub-cleanup.exe" --remove-program "$INSTDIR"' $R0
    ${if} $R0 != 0
      Abort "Program cleanup did not complete. User data is retained."
    ${endif}
    RMDir "$INSTDIR"
  ${endif}
!macroend
