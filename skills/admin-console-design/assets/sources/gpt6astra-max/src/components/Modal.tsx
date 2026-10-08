import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

let openModalCount = 0;
let previousOverflow = '';

interface ModalProps {
  title: string;
  description?: string;
  children: ReactNode;
  onClose: () => void;
  className?: string;
  danger?: boolean;
}

export function Modal({ title, description, children, onClose, className = '', danger = false }: ModalProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const backdropPointer = useRef(false);
  const titleId = useId();
  const descriptionId = useId();
  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const node = dialog.current;
    if (!node) return;
    node.showModal();
    if (openModalCount++ === 0) {
      previousOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
    }
    const frame = requestAnimationFrame(() => node.querySelector<HTMLElement>('[data-autofocus]')?.focus());
    return () => {
      cancelAnimationFrame(frame);
      node.close();
      if (--openModalCount === 0) document.body.style.overflow = previousOverflow;
      requestAnimationFrame(() => {
        if (previousFocus?.isConnected && previousFocus.getClientRects().length) previousFocus.focus({ preventScroll: true });
        else if (openModalCount === 0) (document.querySelector<HTMLElement>('[data-focus-fallback]') || document.getElementById('main-content'))?.focus({ preventScroll: true });
      });
    };
  }, []);

  return createPortal(
    <dialog ref={dialog} className={`modal ${className}`} aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined} role={danger ? 'alertdialog' : 'dialog'}
      onCancel={event => { event.preventDefault(); onClose(); }}
      onPointerDown={event => { backdropPointer.current = event.target === event.currentTarget; }}
      onClick={event => { if (backdropPointer.current && event.target === event.currentTarget) onClose(); }}>
      <div className="modal-inner">
        <header className="modal-header">
          <div><h2 id={titleId}>{title}</h2>{description && <p id={descriptionId}>{description}</p>}</div>
          <button className="icon-button" onClick={onClose} aria-label="关闭弹窗"><X size={19} /></button>
        </header>
        {children}
      </div>
    </dialog>, document.body,
  );
}