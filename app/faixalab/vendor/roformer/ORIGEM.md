# Origem da separação de guitarras

Arquitetura Mel-Band RoFormer: ZFTurbo/Music-Source-Separation-Training e lucidrains, MIT, com adaptações de pedromtcosta/sound-razor (commit d59c0e0aa48993b40ac4bbc15810240a420434ea). As licenças e o NOTICE acompanham o código.

O modelo padrão usa a arquitetura HTDemucs da biblioteca Demucs e o checkpoint Lead/Rhythm de Dry Paint Dealer Undr. A implementação local usa janelas de 3 s e sobreposição de 50%, produzindo duas estimativas, com projeção para preservar a soma original. O modelo alternativo Mel-Band RoFormer de listra92 permanece acessível pela CLI --model listra.

Arquivos de origem: https://huggingface.co/noblebarkrr/mvsepless_resources . Os nomes, URLs e SHA-256 estão em faixalab/lead_rhythm.py. Os checkpoints de guitarras são baixados no primeiro uso e não estão embutidos no ZIP.
