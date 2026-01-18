;;; gp2ytm-draft-helper.el --- Helper functions for editing GP2YTM draft files

;;; Commentary:
;; This file provides helper functions for editing GP2YTM draft JSON files in Emacs.
;;
;; The default keybindings use the prefix "C-c p" but this can be customized
;; by setting `gp2ytm-draft-prefix' to your preferred prefix.
;;
;; Default keybindings:
;; C-c p c - Copy track info to clipboard
;; C-c p t - Toggle include field
;; C-c p n - Move to next track
;; C-c p p - Move to previous track
;; C-c p v - Set video_id from clipboard

;;; Code:

(defgroup gp2ytm nil
  "GP2YTM draft editing tools."
  :group 'tools)

(defun gp2ytm-copy-track-info ()
  "Narrow to current track object, copy bbc_artist and bbc_title to clipboard, then widen."
  (interactive)
  (save-excursion
    (let ((start-pos (point))
          (track-start nil)
          (track-end nil)
          (artist nil)
          (title nil))
      
      ;; Find the start of the current track object
      (save-excursion
        (while (and (not track-start) (> (point) (point-min)))
          (backward-char)
          (when (looking-at "{")
            ;; Check if this is a track object by looking for bbc_artist
            (save-excursion
              (let ((brace-end (save-excursion
                                 (forward-sexp)
                                 (point))))
                (when (search-forward "\"bbc_artist\"" brace-end t)
                  (setq track-start (point-at-bol))))))))
      
      ;; Find the end of the current track object
      (save-excursion
        (goto-char start-pos)
        (while (and (not track-end) (< (point) (point-max)))
          (forward-char)
          (when (looking-at "}")
            ;; Check if this closes our track object
            (save-excursion
              (backward-sexp)
              (when (>= (point) track-start)
                (setq track-end (1+ (point))))))))
      
      (if (and track-start track-end)
          (progn
            ;; Narrow to the track object
            (narrow-to-region track-start track-end)
            
            ;; Extract bbc_artist
            (goto-char (point-min))
            (when (search-forward "\"bbc_artist\"" nil t)
              (search-forward ":" nil t)
              (skip-chars-forward " \t")
              (when (looking-at "\"\\([^\"]*\\)\"")
                (setq artist (match-string 1))))
            
            ;; Extract bbc_title
            (goto-char (point-min))
            (when (search-forward "\"bbc_title\"" nil t)
              (search-forward ":" nil t)
              (skip-chars-forward " \t")
              (when (looking-at "\"\\([^\"]*\\)\"")
                (setq title (match-string 1))))
            
            ;; Copy to clipboard
            (when (and artist title)
              (let ((track-info (concat artist " " title)))
                (kill-new track-info)
                (message "Copied to clipboard: %s" track-info)))
            
            ;; Remove narrowing
            (widen))
        
        (message "Could not find track object boundaries")))))

(defun gp2ytm-toggle-include ()
  "Toggle the 'include' field of the current track between true and false."
  (interactive)
  (save-excursion
    (let ((start-pos (point))
          (track-start nil)
          (track-end nil))
      
      ;; Find the start of the current track object
      (save-excursion
        (while (and (not track-start) (> (point) (point-min)))
          (backward-char)
          (when (looking-at "{")
            ;; Check if this is a track object by looking for bbc_artist
            (save-excursion
              (let ((brace-end (save-excursion
                                 (forward-sexp)
                                 (point))))
                (when (search-forward "\"bbc_artist\"" brace-end t)
                  (setq track-start (point-at-bol))))))))
      
      ;; Find the end of the current track object
      (save-excursion
        (goto-char start-pos)
        (while (and (not track-end) (< (point) (point-max)))
          (forward-char)
          (when (looking-at "}")
            ;; Check if this closes our track object
            (save-excursion
              (backward-sexp)
              (when (>= (point) track-start)
                (setq track-end (1+ (point))))))))
      
      (if (and track-start track-end)
          (progn
            ;; Narrow to the track object
            (narrow-to-region track-start track-end)
            
            ;; Find and toggle the include field
            (goto-char (point-min))
            (if (search-forward "\"include\"" nil t)
                (progn
                  (search-forward ":" nil t)
                  (skip-chars-forward " \t")
                  (cond
                   ((looking-at "true")
                    (replace-match "false")
                    (message "Set include to false"))
                   ((looking-at "false")
                    (replace-match "true")
                    (message "Set include to true"))
                   (t
                    (message "Could not parse include value"))))
              (message "Could not find include field"))
            
            ;; Remove narrowing
            (widen))
        
        (message "Could not find track object boundaries")))))

(defun gp2ytm-next-track ()
  "Move to the next track object in the JSON file."
  (interactive)
  (let ((current-pos (point)))
    (if (search-forward "\"bbc_artist\"" nil t)
        (progn
          (beginning-of-line)
          (message "Moved to next track"))
      (goto-char current-pos)
      (message "No more tracks found"))))

(defun gp2ytm-prev-track ()
  "Move to the previous track object in the JSON file."
  (interactive)
  (let ((current-pos (point)))
    (if (search-backward "\"bbc_artist\"" nil t)
        (progn
          (beginning-of-line)
          (message "Moved to previous track"))
      (goto-char current-pos)
      (message "No previous tracks found"))))

(defun gp2ytm-set-video-id ()
  "Set the video_id field of the current track to the value from clipboard."
  (interactive)
  (save-excursion
    (let ((start-pos (point))
          (track-start nil)
          (track-end nil)
          (clipboard-content (current-kill 0)))
      
      ;; Find the start of the current track object
      (save-excursion
        (while (and (not track-start) (> (point) (point-min)))
          (backward-char)
          (when (looking-at "{")
            ;; Check if this is a track object by looking for bbc_artist
            (save-excursion
              (let ((brace-end (save-excursion
                                 (forward-sexp)
                                 (point))))
                (when (search-forward "\"bbc_artist\"" brace-end t)
                  (setq track-start (point-at-bol))))))))
      
      ;; Find the end of the current track object
      (save-excursion
        (goto-char start-pos)
        (while (and (not track-end) (< (point) (point-max)))
          (forward-char)
          (when (looking-at "}")
            ;; Check if this closes our track object
            (save-excursion
              (backward-sexp)
              (when (>= (point) track-start)
                (setq track-end (1+ (point))))))))
      
      (if (and track-start track-end)
          (progn
            ;; Narrow to the track object
            (narrow-to-region track-start track-end)
            
            ;; Find and update the video_id field
            (goto-char (point-min))
            (if (search-forward "\"video_id\"" nil t)
                (progn
                  (search-forward ":" nil t)
                  (skip-chars-forward " \t")
                  ;; Replace the current value (null, string, etc.) with clipboard content
                  (let ((video-id-updated nil))
                    (cond
                     ((looking-at "null")
                      (replace-match (format "\"%s\"" clipboard-content))
                      (setq video-id-updated t)
                      (message "Set video_id to: %s" clipboard-content))
                     ((looking-at "\"[^\"]*\"")
                      (replace-match (format "\"%s\"" clipboard-content))
                      (setq video-id-updated t)
                      (message "Updated video_id to: %s" clipboard-content))
                     (t
                      (message "Could not parse video_id value")))
                    
                    ;; If video_id was successfully updated, also set include to true
                    (when video-id-updated
                      (goto-char (point-min))
                      (when (search-forward "\"include\"" nil t)
                        (search-forward ":" nil t)
                        (skip-chars-forward " \t")
                        (cond
                         ((looking-at "false")
                          (replace-match "true")
                          (message "Set video_id to: %s and include to true" clipboard-content))
                         ((looking-at "true")
                          (message "Set video_id to: %s (include already true)" clipboard-content))
                         (t
                          (message "Set video_id to: %s but could not update include field" clipboard-content)))))))
              (message "Could not find video_id field"))
            
            ;; Remove narrowing
            (widen))
        
        (message "Could not find track object boundaries")))))

;; Customizable prefix for GP2YTM keybindings
(defcustom gp2ytm-draft-prefix "C-c p"
  "Prefix key for GP2YTM draft mode commands."
  :type 'string
  :group 'gp2ytm)

;; Define a minor mode for GP2YTM draft editing
(defvar gp2ytm-draft-mode-map
  (let ((map (make-sparse-keymap)))
    ;; We'll set up the keybindings dynamically based on the prefix
    map)
  "Keymap for GP2YTM draft mode.")

(defun gp2ytm-setup-keybindings ()
  "Set up keybindings for GP2YTM draft mode using the configured prefix."
  (let ((map gp2ytm-draft-mode-map)
        (prefix gp2ytm-draft-prefix))
    ;; Clear existing bindings
    (setcdr map nil)
    ;; Set up new bindings with the configured prefix
    (define-key map (kbd (concat prefix " c")) 'gp2ytm-copy-track-info)
    (define-key map (kbd (concat prefix " t")) 'gp2ytm-toggle-include)
    (define-key map (kbd (concat prefix " n")) 'gp2ytm-next-track)
    (define-key map (kbd (concat prefix " p")) 'gp2ytm-prev-track)
    (define-key map (kbd (concat prefix " v")) 'gp2ytm-set-video-id)))

;; Set up initial keybindings
(gp2ytm-setup-keybindings)

;; Update keybindings when the prefix is customized
(defun gp2ytm-update-prefix ()
  "Update keybindings when the prefix is changed."
  (gp2ytm-setup-keybindings))

(add-hook 'gp2ytm-draft-prefix-changed-hook 'gp2ytm-update-prefix)

(define-minor-mode gp2ytm-draft-mode
  "Minor mode for editing GP2YTM draft JSON files.

Key bindings (with default prefix 'C-c p'):
\\<gp2ytm-draft-mode-map>
\\[gp2ytm-copy-track-info] - Copy track info to clipboard
\\[gp2ytm-toggle-include] - Toggle include field
\\[gp2ytm-next-track] - Move to next track
\\[gp2ytm-prev-track] - Move to previous track
\\[gp2ytm-set-video-id] - Set video_id from clipboard

The prefix can be customized by setting `gp2ytm-draft-prefix'."
  :lighter " GP2YTM"
  :keymap gp2ytm-draft-mode-map
  :group 'gp2ytm
  ;; Set up keybindings when the mode is enabled
  (when gp2ytm-draft-mode
    (gp2ytm-setup-keybindings)))

;; Auto-enable the mode for .json files that look like GP2YTM drafts
(defun gp2ytm-maybe-enable-draft-mode ()
  "Enable gp2ytm-draft-mode if the current buffer looks like a GP2YTM draft file."
  (when (and (string-match "\\.json\\'" (or buffer-file-name ""))
             (save-excursion
               (goto-char (point-min))
               (search-forward "\"bbc_artist\"" nil t)))
    (gp2ytm-draft-mode 1)))

(add-hook 'json-mode-hook 'gp2ytm-maybe-enable-draft-mode)
(add-hook 'js-mode-hook 'gp2ytm-maybe-enable-draft-mode)

(provide 'gp2ytm-draft-helper)

;;; gp2ytm-draft-helper.el ends here
